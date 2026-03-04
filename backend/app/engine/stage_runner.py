from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.openai_client import ENFORCED_OPENAI_MODEL, OpenAIClient


@dataclass(slots=True)
class StageConfig:
    stage: str
    max_tokens: int
    reasoning_effort: str
    response_format: dict[str, Any]


@dataclass(slots=True)
class StageRunResult:
    payload: dict[str, Any]
    attempts: int
    usage: dict[str, Any]


class StageError(RuntimeError):
    def __init__(self, *, stage: str, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.stage = stage
        self.code = code
        self.message = message
        self.details = details or {}


def _parse_message_content(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text") or ""))
        content = "".join(text_parts)
    text = str(content or "").strip()
    if not text:
        return {}
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        fenced = text.strip().strip("`")
        out = json.loads(fenced)
    if not isinstance(out, dict):
        raise ValueError("json_root_not_object")
    return out


def _repair_messages(messages: list[dict[str, str]], raw_output: str, schema: dict[str, Any]) -> list[dict[str, str]]:
    schema_payload = schema.get("json_schema", {}).get("schema", schema)
    return [
        {
            "role": "system",
            "content": "Return only valid JSON that matches the provided schema exactly.",
        },
        {
            "role": "user",
            "content": (
                "The following JSON is invalid or missing required fields. "
                "Fix it to match the schema and return only the corrected JSON.\n"
                f"Schema:\n{json.dumps(schema_payload, ensure_ascii=True)}\n"
                f"Invalid output:\n{raw_output}"
            ),
        },
    ]


async def run_stage(
    *,
    openai: OpenAIClient,
    config: StageConfig,
    messages: list[dict[str, str]],
    validator: Callable[[dict[str, Any]], None] | None = None,
    timeout_seconds: float = 25.0,
) -> StageRunResult:
    attempts = 0
    usage: dict[str, Any] = {}
    last_raw = ""

    async def _call(request_messages: list[dict[str, str]]) -> tuple[dict[str, Any], dict[str, Any], str]:
        response = await openai.chat_completion(
            model=ENFORCED_OPENAI_MODEL,
            messages=request_messages,
            reasoning_effort=config.reasoning_effort,
            max_completion_tokens=config.max_tokens,
            response_format=config.response_format,
            timeout_seconds=timeout_seconds,
        )
        message = dict(response.get("message") or {})
        text = str(message.get("content") or "")
        payload = _parse_message_content(message)
        return payload, dict(response.get("usage") or {}), text

    for is_repair in (False, True):
        try:
            attempts += 1
            call_messages = messages if not is_repair else _repair_messages(messages, last_raw, config.response_format)
            payload, usage_payload, raw_text = await _call(call_messages)
            usage = usage_payload or usage
            last_raw = raw_text
            if validator is not None:
                validator(payload)
            return StageRunResult(payload=payload, attempts=attempts, usage=usage)
        except Exception as exc:  # noqa: BLE001
            if not is_repair:
                if not last_raw:
                    last_raw = str(exc)
                continue
            raise StageError(
                stage=config.stage,
                code="STAGE_JSON_OR_VALIDATION_FAILED",
                message=f"{config.stage} failed after repair attempt",
                details={"error": str(exc)},
            ) from exc

    raise StageError(
        stage=config.stage,
        code="STAGE_UNKNOWN_FAILURE",
        message=f"{config.stage} failed",
        details={},
    )
