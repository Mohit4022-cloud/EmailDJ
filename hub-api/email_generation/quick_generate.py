"""Quick-generate path with mock/real mode support."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import AsyncGenerator

import httpx

from context_vault.models import AccountContext
from email_generation.model_cascade import get_model
from email_generation.prompt_templates import get_quick_generate_prompt

logger = logging.getLogger(__name__)


async def _mock_stream(text: str) -> AsyncGenerator[str, None]:
    for token in text.split(" "):
        await asyncio.sleep(0.02)
        yield token + " "


def _mode() -> str:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() or "mock"


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


async def _real_generate(prompt: list[dict[str, str]], throttled: bool = False) -> str:
    preferred = os.environ.get("EMAILDJ_REAL_PROVIDER", "openai").lower()
    model = get_model(tier=2, task="quick_generate", throttled=throttled)

    logger.info(
        "quick_generate_model_selected",
        extra={"provider": model.provider, "model": model.model_name, "tier": model.tier, "preferred": preferred},
    )

    if preferred == "anthropic":
        return await _anthropic_messages(prompt, "claude-3-5-haiku-latest")
    if preferred == "groq":
        return await _groq_chat_completion(prompt, "llama-3.3-70b-versatile")
    return await _openai_chat_completion(prompt, "gpt-4o-mini")


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
    try:
        output = await _real_generate(prompt=prompt, throttled=throttled)
    except Exception as exc:
        logger.exception("quick_generate_real_failed")
        output = f"Subject: Quick idea\n\nUnable to reach provider in real mode ({exc})."

    words = output.split(" ")
    first = True
    for token in words:
        if first:
            logger.info("quick_generate_ttft", extra={"ttft_ms": int((time.perf_counter() - start) * 1000), "mode": "real"})
            first = False
        yield token + " "

    logger.info("quick_generate_total", extra={"duration_ms": int((time.perf_counter() - start) * 1000), "mode": "real"})
