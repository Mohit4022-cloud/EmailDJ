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
        ModelSpec(tier=2, provider="openai", model_name="gpt-5-nano", temperature=0.0, timeout_seconds=3.0),
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


@pytest.mark.asyncio
async def test_real_generate_stops_on_openai_success_without_provider_fallback(monkeypatch):
    from email_generation.model_cascade import ModelSpec
    import email_generation.quick_generate as qg

    monkeypatch.setenv("REDIS_FORCE_INMEMORY", "1")
    sequence = [
        ModelSpec(tier=1, provider="openai", model_name="gpt-5-nano", temperature=0.0, timeout_seconds=3.0),
        ModelSpec(tier=1, provider="anthropic", model_name="claude-3-5-haiku-latest", temperature=None, timeout_seconds=3.0),
        ModelSpec(tier=1, provider="groq", model_name="llama-3.3-70b-versatile", temperature=0.0, timeout_seconds=3.0),
    ]
    monkeypatch.setattr(qg, "get_cascade_sequence", lambda task, throttled=False: sequence)
    monkeypatch.setattr(qg, "_provider_max_retries", lambda provider: 1)

    calls = {"openai": 0, "anthropic": 0, "groq": 0}

    async def fake_openai(prompt, model_name, timeout=30.0, max_output_tokens=None, strict_json=False):  # noqa: ARG001
        calls["openai"] += 1
        return '{"subject":"S","body":"B"}', "stop"

    async def fake_anthropic(prompt, model_name, timeout=35.0, max_output_tokens=None):  # noqa: ARG001
        calls["anthropic"] += 1
        return "should_not_be_used", "stop"

    async def fake_groq(prompt, model_name, timeout=20.0, max_output_tokens=None):  # noqa: ARG001
        calls["groq"] += 1
        return "should_not_be_used", "stop"

    monkeypatch.setattr(qg, "_openai_chat_completion", fake_openai)
    monkeypatch.setattr(qg, "_anthropic_messages", fake_anthropic)
    monkeypatch.setattr(qg, "_groq_chat_completion", fake_groq)

    result = await qg._real_generate(
        prompt=[{"role": "user", "content": "Return JSON"}],
        task="quick_generate",
        throttled=False,
    )

    assert result.provider == "openai"
    assert result.cascade_reason == "primary"
    assert result.attempt_count == 1
    assert calls == {"openai": 1, "anthropic": 0, "groq": 0}


def test_output_token_budget_adds_web_mvp_headroom(monkeypatch):
    import email_generation.remix_engine as remix_engine

    monkeypatch.setattr(remix_engine, "web_mvp_output_token_budget_default", lambda: 420)

    assert remix_engine._output_token_budget({"length_short_long": 50}) == 560


def test_output_token_budget_keeps_higher_override(monkeypatch):
    import email_generation.remix_engine as remix_engine

    monkeypatch.setattr(remix_engine, "web_mvp_output_token_budget_default", lambda: 640)

    assert remix_engine._output_token_budget({"length_short_long": 50}) == 640


class _DummyResponse:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_openai_chat_completion_uses_drafting_effort_and_omits_temperature_for_gpt5(monkeypatch):
    import email_generation.quick_generate as qg

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict = {}
    reasoning_calls: list[dict] = []

    def fake_openai_reasoning_effort(*, raw_env_vars=None, model_name=None, transform_type=None):  # noqa: ARG001
        reasoning_calls.append({"model_name": model_name, "transform_type": transform_type})
        return "low"

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ARG002
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _DummyResponse(
                {
                    "choices": [
                        {
                            "message": {"content": [{"type": "text", "text": "{\"subject\":\"S\",\"body\":\"B\"}"}]},
                            "finish_reason": "stop",
                        }
                    ]
                }
            )

    monkeypatch.setattr(qg, "openai_reasoning_effort", fake_openai_reasoning_effort)
    monkeypatch.setattr(qg.httpx, "AsyncClient", FakeAsyncClient)

    text, finish_reason = await qg._openai_chat_completion(
        prompt=[{"role": "user", "content": "Return JSON"}],
        model_name="gpt-5-nano",
    )

    assert finish_reason == "stop"
    assert text == "{\"subject\":\"S\",\"body\":\"B\"}"
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["json"]["reasoning_effort"] == "low"
    assert "temperature" not in captured["json"]
    assert reasoning_calls == [{"model_name": "gpt-5-nano", "transform_type": "drafting"}]


@pytest.mark.asyncio
async def test_openai_chat_completion_keeps_temperature_for_non_gpt5(monkeypatch):
    import email_generation.quick_generate as qg

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("EMAILDJ_OPENAI_REASONING_EFFORT", raising=False)
    monkeypatch.setenv("EMAILDJ_OPENAI_REASONING_EFFORT_DRAFT", "low")
    captured: dict = {}

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ARG002
            return None

        async def post(self, url, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _DummyResponse(
                {
                    "choices": [
                        {
                            "message": {"content": "{\"subject\":\"S\",\"body\":\"B\"}"},
                            "finish_reason": "stop",
                        }
                    ]
                }
            )

    monkeypatch.setattr(qg.httpx, "AsyncClient", FakeAsyncClient)

    _, finish_reason = await qg._openai_chat_completion(
        prompt=[{"role": "user", "content": "Return JSON"}],
        model_name="gpt-4.1-mini",
    )

    assert finish_reason == "stop"
    assert captured["json"]["temperature"] == 0
    assert captured["json"]["reasoning_effort"] == "low"
