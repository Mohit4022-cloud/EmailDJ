from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))


@pytest.mark.asyncio
async def test_real_generate_retries_when_provider_stops_due_to_length(monkeypatch):
    from email_generation.model_cascade import ModelSpec
    import email_generation.quick_generate as qg

    monkeypatch.setenv("REDIS_FORCE_INMEMORY", "1")

    sequence = [
        ModelSpec(tier=2, provider="openai", model_name="gpt-4.1-nano", temperature=0.0, timeout_seconds=3.0),
    ]
    monkeypatch.setattr(qg, "get_cascade_sequence", lambda task, throttled=False: sequence)
    monkeypatch.setattr(qg, "_provider_max_retries", lambda provider: 2)

    calls = {"count": 0}

    async def fake_openai(prompt, model_name, timeout=30.0, max_output_tokens=None, strict_json=False):  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] == 1:
            return '{"subject":"s","body":"b"}', "length"
        return '{"subject":"Final","body":"Complete body."}', "stop"

    monkeypatch.setattr(qg, "_openai_chat_completion", fake_openai)

    result = await qg._real_generate(
        prompt=[{"role": "user", "content": "Return JSON"}],
        task="web_mvp",
        throttled=False,
        output_token_budget=180,
    )

    assert calls["count"] == 2
    assert result.finish_reason == "stop"
    assert result.provider == "openai"
    assert result.attempt_count == 2
