from __future__ import annotations

import json
from typing import Any

import httpx

from app.config import Settings


class OpenAIClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def enabled(self) -> bool:
        return bool(self.settings.openai_api_key and not self.settings.provider_stub_enabled)

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        reasoning_effort: str,
        max_completion_tokens: int = 800,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("openai_unavailable")

        payload: dict[str, Any] = {
            "model": self.settings.openai_model,
            "messages": messages,
            "reasoning_effort": reasoning_effort,
            "max_completion_tokens": max_completion_tokens,
        }
        if tools:
            payload["tools"] = tools
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        if response_format is not None:
            payload["response_format"] = response_format

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        resp.raise_for_status()
        data = resp.json()
        choice = (data.get("choices") or [{}])[0]
        return {
            "message": choice.get("message") or {},
            "finish_reason": choice.get("finish_reason"),
            "usage": data.get("usage") or {},
            "raw": data,
        }

    async def chat_json(
        self,
        *,
        messages: list[dict[str, Any]],
        reasoning_effort: str,
        schema_name: str,
        schema: dict[str, Any],
        max_completion_tokens: int = 1000,
    ) -> dict[str, Any]:
        response = await self.chat_completion(
            messages=messages,
            reasoning_effort=reasoning_effort,
            max_completion_tokens=max_completion_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        )
        content = str((response.get("message") or {}).get("content") or "").strip()
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Some responses can still include quoted JSON string.
            maybe = content.strip('`')
            try:
                return json.loads(maybe)
            except json.JSONDecodeError:
                return {}
