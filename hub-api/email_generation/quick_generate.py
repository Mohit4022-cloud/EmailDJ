"""Quick-generate path with mock/real mode support."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx

from context_vault.models import AccountContext
from infra.alerting import emit_provider_failure_alert
from email_generation.model_cascade import get_model
from email_generation.prompt_templates import get_quick_generate_prompt
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)


async def _mock_stream(text: str) -> AsyncGenerator[str, None]:
    for token in text.split(" "):
        await asyncio.sleep(0.02)
        yield token + " "


def _mode() -> str:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() or "mock"


def _preferred_provider() -> str:
    return os.environ.get("EMAILDJ_REAL_PROVIDER", "openai").strip().lower() or "openai"


async def _openai_chat_completion(prompt: list[dict[str, str]], model_name: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model_name, "messages": prompt, "temperature": 0},
        )
    res.raise_for_status()
    data = res.json()
    return data["choices"][0]["message"]["content"]


async def _anthropic_messages(prompt: list[dict[str, str]], model_name: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY missing")

    system = ""
    messages = []
    for m in prompt:
        if m.get("role") == "system":
            system = m.get("content", "")
        else:
            messages.append({"role": m.get("role", "user"), "content": m.get("content", "")})

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={"model": model_name, "system": system, "messages": messages, "max_tokens": 400},
        )
    res.raise_for_status()
    data = res.json()
    parts = data.get("content", [])
    return "".join(part.get("text", "") for part in parts if isinstance(part, dict))


async def _groq_chat_completion(prompt: list[dict[str, str]], model_name: str) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing")

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model_name, "messages": prompt, "temperature": 0},
        )
    res.raise_for_status()
    data = res.json()
    return data["choices"][0]["message"]["content"]


async def _record_provider_failure(provider: str, error: str) -> None:
    redis = get_redis()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"quick_provider_failures:{provider}:{day}"
    alert_last_key = f"quick_provider_failure_alert_last:{provider}:{day}"
    raw = await redis.get(key)
    count = int(raw or 0) + 1
    await redis.set(key, str(count))

    threshold = int(os.environ.get("QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD", "5"))
    alert_step = int(os.environ.get("QUICK_PROVIDER_FAILURE_ALERT_STEP", "5"))
    if alert_step <= 0:
        alert_step = 5
    logger.error(
        "quick_generate_provider_failed",
        extra={"provider": provider, "failure_count": count, "error": error},
    )
    if count >= threshold:
        logger.warning(
            "quick_generate_provider_failure_threshold_exceeded",
            extra={"provider": provider, "failure_count": count, "threshold": threshold, "alert_step": alert_step},
        )
        raw_last = await redis.get(alert_last_key)
        last_alert_count = int(raw_last) if raw_last is not None else None
        should_alert = last_alert_count is None or count >= (last_alert_count + alert_step)
        if should_alert:
            payload = {
                "event": "quick_provider_failure_threshold_exceeded",
                "provider": provider,
                "failure_count": count,
                "threshold": threshold,
                "alert_step": alert_step,
                "date_utc": day,
                "timestamp_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "environment": os.environ.get("APP_ENV", "local").strip() or "local",
                "service": "hub-api",
                "error_sample": error,
            }
            await emit_provider_failure_alert(payload)
            await redis.set(alert_last_key, str(count))


async def _real_generate(prompt: list[dict[str, str]], throttled: bool = False) -> str:
    preferred = _preferred_provider()
    model = get_model(tier=2, task="quick_generate", throttled=throttled)

    logger.info(
        "quick_generate_model_selected",
        extra={"provider": model.provider, "model": model.model_name, "tier": model.tier, "preferred": preferred},
    )

    if preferred == "anthropic":
        return await _anthropic_messages(prompt, "claude-3-5-haiku-latest")
    if preferred == "groq":
        return await _groq_chat_completion(prompt, "llama-3.3-70b-versatile")
    return await _openai_chat_completion(prompt, "gpt-4.1-nano")


async def quick_generate(
    payload: dict,
    account_context: AccountContext | None,
    slider_value: int,
    throttled: bool = False,
    use_mock: bool | None = None,
) -> AsyncGenerator[str, None]:
    mode = _mode()
    if use_mock is None:
        use_mock = mode != "real"

    start = time.perf_counter()
    prompt = get_quick_generate_prompt(payload=payload, account_context=account_context, slider_value=slider_value)

    if use_mock:
        account = payload.get("accountName") or payload.get("accountId") or "your team"
        style = "highly personalized" if slider_value >= 8 else "concise"
        dummy = (
            f"Subject: Quick idea for {account}\n\n"
            f"Hi there, I noticed a few priorities in your account context. "
            f"Here is a {style} draft that focuses on one clear outcome and a low-friction CTA. "
            "If useful, I can share a tailored 2-minute walkthrough for your team this week."
        )
        logger.info("quick_generate_mode", extra={"mode": "mock"})
        first = True
        for token in dummy.split(" "):
            await asyncio.sleep(0.02)
            if first:
                logger.info("quick_generate_ttft", extra={"ttft_ms": int((time.perf_counter() - start) * 1000), "mode": "mock"})
                first = False
            yield token + " "
        return

    logger.info("quick_generate_mode", extra={"mode": "real"})
    provider = _preferred_provider()
    try:
        output = await _real_generate(prompt=prompt, throttled=throttled)
    except Exception as exc:
        await _record_provider_failure(provider=provider, error=str(exc))
        output = f"Subject: Quick idea\n\nUnable to reach provider in real mode ({exc})."

    words = output.split(" ")
    first = True
    for token in words:
        if first:
            logger.info("quick_generate_ttft", extra={"ttft_ms": int((time.perf_counter() - start) * 1000), "mode": "real"})
            first = False
        yield token + " "

    logger.info("quick_generate_total", extra={"duration_ms": int((time.perf_counter() - start) * 1000), "mode": "real"})
