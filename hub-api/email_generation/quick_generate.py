"""Quick-generate path with mock/real mode support."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import AsyncGenerator

import httpx

from context_vault.models import AccountContext
from infra.alerting import emit_provider_failure_alert
from email_generation.model_cascade import _provider_max_retries, get_cascade_sequence
from email_generation.prompt_templates import get_quick_generate_prompt
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

_CASCADE_TTL = 3 * 24 * 60 * 60  # 3 days


@dataclass
class GenerateResult:
    text: str
    provider: str
    model_name: str
    cascade_reason: str  # "primary" | "throttled" | "fallback_after_{provider}_error"
    attempt_count: int


async def _mock_stream(text: str) -> AsyncGenerator[str, None]:
    for token in text.split(" "):
        await asyncio.sleep(0.02)
        yield token + " "


def _mode() -> str:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() or "mock"


def _preferred_provider() -> str:
    return os.environ.get("EMAILDJ_REAL_PROVIDER", "openai").strip().lower() or "openai"


async def _openai_chat_completion(prompt: list[dict[str, str]], model_name: str, timeout: float = 30.0) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY missing")

    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": model_name, "messages": prompt, "temperature": 0},
        )
    res.raise_for_status()
    data = res.json()
    return data["choices"][0]["message"]["content"]


async def _anthropic_messages(prompt: list[dict[str, str]], model_name: str, timeout: float = 35.0) -> str:
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

    async with httpx.AsyncClient(timeout=timeout) as client:
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


async def _groq_chat_completion(prompt: list[dict[str, str]], model_name: str, timeout: float = 20.0) -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing")

    async with httpx.AsyncClient(timeout=timeout) as client:
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


async def _real_generate(
    prompt: list[dict[str, str]],
    task: str = "quick_generate",
    throttled: bool = False,
) -> GenerateResult:
    """Cascade through providers in order, retrying per budget, returning on first success."""
    sequence = get_cascade_sequence(task=task, throttled=throttled)
    redis = get_redis()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    attempt_count = 0
    failed_providers: list[str] = []

    for idx, spec in enumerate(sequence):
        if throttled:
            cascade_reason = "throttled"
        elif idx == 0:
            cascade_reason = "primary"
        else:
            cascade_reason = f"fallback_after_{failed_providers[-1]}_error"

        max_retries = _provider_max_retries(spec.provider)
        for attempt in range(max_retries):
            attempt_count += 1
            attempt_key = f"cascade:provider_attempt:{spec.provider}:{day}"
            await redis.incr(attempt_key)
            await redis.expire(attempt_key, _CASCADE_TTL)

            logger.info(
                "quick_generate_model_selected",
                extra={
                    "provider": spec.provider,
                    "model": spec.model_name,
                    "tier": spec.tier,
                    "attempt": attempt + 1,
                    "cascade_reason": cascade_reason,
                },
            )

            try:
                if spec.provider == "anthropic":
                    text = await _anthropic_messages(prompt, spec.model_name, timeout=spec.timeout_seconds)
                elif spec.provider == "groq":
                    text = await _groq_chat_completion(prompt, spec.model_name, timeout=spec.timeout_seconds)
                else:
                    text = await _openai_chat_completion(prompt, spec.model_name, timeout=spec.timeout_seconds)

                success_key = f"cascade:provider_success:{spec.provider}:{day}"
                await redis.incr(success_key)
                await redis.expire(success_key, _CASCADE_TTL)

                return GenerateResult(
                    text=text,
                    provider=spec.provider,
                    model_name=spec.model_name,
                    cascade_reason=cascade_reason,
                    attempt_count=attempt_count,
                )
            except Exception as exc:
                await _record_provider_failure(provider=spec.provider, error=str(exc))

        # All retries for this provider exhausted — record fallback and move on
        failed_providers.append(spec.provider)
        if idx + 1 < len(sequence):
            fallback_key = f"cascade:fallback_triggered:{spec.provider}:{day}"
            await redis.incr(fallback_key)
            await redis.expire(fallback_key, _CASCADE_TTL)

    raise RuntimeError(f"all_cascade_providers_failed:{','.join(failed_providers)}")


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
            f"Subject: [MOCK DRAFT] Quick idea for {account}\n\n"
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
    try:
        result = await _real_generate(prompt=prompt, throttled=throttled)
        output = result.text
    except Exception as exc:
        output = f"Subject: Quick idea\n\nUnable to reach provider in real mode ({exc})."
        result = None

    words = output.split(" ")
    first = True
    for token in words:
        if first:
            logger.info("quick_generate_ttft", extra={"ttft_ms": int((time.perf_counter() - start) * 1000), "mode": "real"})
            first = False
        yield token + " "

    logger.info(
        "quick_generate_total",
        extra={
            "duration_ms": int((time.perf_counter() - start) * 1000),
            "mode": "real",
            "provider": result.provider if result else "none",
            "model": result.model_name if result else "none",
            "cascade_reason": result.cascade_reason if result else "all_failed",
            "attempt_count": result.attempt_count if result else 0,
        },
    )
