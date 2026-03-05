from __future__ import annotations

import json
from typing import Any

import pytest

from app.engine.stage_runner import StageConfig, StageError, run_stage


class StubOpenAI:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    async def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        payload = self.responses.pop(0) if self.responses else {}
        content = payload if isinstance(payload, str) else json.dumps(payload)
        return {"message": {"content": content}, "usage": {"total_tokens": 10}}


def _response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "TestDraft",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["version", "subject", "body"],
                "properties": {
                    "version": {"type": "string", "minLength": 1},
                    "subject": {"type": "string", "minLength": 1},
                    "body": {"type": "string", "minLength": 1},
                },
            },
        },
    }


def _nullable_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "NullableDraft",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": ["version", "proof_line"],
                "properties": {
                    "version": {"type": "string", "minLength": 1},
                    "proof_line": {
                        "oneOf": [
                            {"type": "string", "minLength": 1},
                            {"type": "null"},
                        ]
                    },
                },
            },
        },
    }


@pytest.mark.asyncio
async def test_run_stage_repairs_after_schema_failure() -> None:
    openai = StubOpenAI(
        responses=[
            {"version": "1", "subject": "Hello"},  # missing body
            {"version": "1", "subject": "Hello", "body": "World"},
        ]
    )
    result = await run_stage(
        openai=openai,  # type: ignore[arg-type]
        config=StageConfig(
            stage="EMAIL_GENERATION",
            max_tokens=100,
            reasoning_effort="low",
            response_format=_response_format(),
        ),
        messages=[{"role": "system", "content": "Return JSON."}],
        validator=None,
    )

    assert result.attempts == 2
    assert result.payload["body"] == "World"
    assert len(openai.calls) == 2


@pytest.mark.asyncio
async def test_run_stage_fails_after_repair_when_still_schema_invalid() -> None:
    openai = StubOpenAI(
        responses=[
            {"version": "1", "subject": "Hello"},  # missing body
            {"version": "1", "subject": "Still missing"},  # missing body again
        ]
    )

    with pytest.raises(StageError) as exc_info:
        await run_stage(
            openai=openai,  # type: ignore[arg-type]
            config=StageConfig(
                stage="EMAIL_GENERATION",
                max_tokens=100,
                reasoning_effort="low",
                response_format=_response_format(),
            ),
            messages=[{"role": "system", "content": "Return JSON."}],
            validator=None,
        )

    err = exc_info.value
    assert err.code == "STAGE_JSON_OR_VALIDATION_FAILED"
    assert err.stage == "EMAIL_GENERATION"
    assert "first_error" in err.details
    assert len(openai.calls) == 2


@pytest.mark.asyncio
async def test_run_stage_allows_nullable_field_via_oneof() -> None:
    openai = StubOpenAI(
        responses=[
            {"version": "1", "proof_line": None},
        ]
    )
    result = await run_stage(
        openai=openai,  # type: ignore[arg-type]
        config=StageConfig(
            stage="ONE_LINER_COMPRESSOR",
            max_tokens=100,
            reasoning_effort="low",
            response_format=_nullable_response_format(),
        ),
        messages=[{"role": "system", "content": "Return JSON."}],
        validator=None,
    )

    assert result.attempts == 1
    assert "proof_line" in result.payload and result.payload["proof_line"] is None
