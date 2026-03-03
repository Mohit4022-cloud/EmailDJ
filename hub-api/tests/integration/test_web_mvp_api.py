import json
import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))


def _headers():
    return {"x-emaildj-beta-key": "test-key"}


def _generate_payload(company_context=None):
    payload = {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "research_text": (
            "Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts."
        ),
        "offer_lock": "Remix Studio",
        "cta_offer_lock": "",
        "cta_type": "question",
        "style_profile": {
            "formality": 0.1,
            "orientation": -0.4,
            "length": -0.3,
            "assertiveness": 0.2,
        },
    }
    if company_context:
        payload["company_context"] = company_context
    return payload


def _preview_batch_payload():
    return {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "company_url": "https://acme.com",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        "product_context": {
            "product_name": "Remix Studio",
            "one_line_value": "improve SDR reply quality with controllable personalization",
            "proof_points": ["Prospect Enrichment", "Sequence QA"],
            "target_outcome": "15-minute meeting",
        },
        "raw_research": {
            "deep_research_paste": (
                "Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts."
            ),
            "company_notes": "Corsearch helps SDR teams raise reply quality while preserving message control.",
            "extra_constraints": None,
        },
        "global_sliders": {
            "formality": 45,
            "brevity": 65,
            "directness": 70,
            "personalization": 75,
        },
        "presets": [
            {
                "preset_id": "challenger",
                "label": "The Challenger",
                "slider_overrides": {"directness": 85, "brevity": 75},
            },
            {
                "preset_id": "warm_intro",
                "label": "The Warm Intro",
                "slider_overrides": {"formality": 55, "personalization": 80},
            },
        ],
        "offer_lock": "Remix Studio",
        "cta_lock": "Open to a quick chat to see if this is relevant?",
    }


def _stream_token_text(stream_text: str) -> str:
    tokens: list[str] = []
    for line in stream_text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[6:])
        token = payload.get("token")
        if token:
            tokens.append(token)
    return "".join(tokens)


def _stream_token_json(stream_text: str) -> dict:
    return json.loads(_stream_token_text(stream_text))


def _stream_done_payload(stream_text: str) -> dict:
    event_name = ""
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if line.startswith("data: ") and event_name == "done":
            return json.loads(line[6:])
    return {}


def _stream_events(stream_text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = ""
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if line.startswith("data: "):
            events.append((event_name or "message", json.loads(line[6:])))
    return events


def _assert_upgraded_cta(text: str) -> None:
    lower = text.lower()
    assert "worth a look / not a priority?" in lower
    assert ("15-min" in lower) or ("20-min" in lower)
    assert ("teardown" in lower) or ("workflow" in lower) or ("examples" in lower)


@pytest.mark.asyncio
async def test_web_generate_and_remix_stream_flow():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=_generate_payload(), headers=_headers())
        assert start.status_code == 200
        body = start.json()
        assert body["session_id"]
        assert body["request_id"]

        stream = await client.get(f"/web/v1/stream/{body['request_id']}", headers=_headers())
        assert stream.status_code == 200
        assert "event: start" in stream.text
        assert "event: done" in stream.text
        for event_name, payload in _stream_events(stream.text):
            if event_name in {"start", "token", "done", "error"}:
                assert isinstance(payload.get("generation_id"), str) and payload["generation_id"]
                assert isinstance(payload.get("draft_id"), int)
        generated = _stream_token_text(stream.text)
        assert "Acme" in generated
        _assert_upgraded_cta(generated)
        assert "Subject:" in generated
        assert "Body:" in generated
        done = _stream_done_payload(stream.text)
        assert done["request_id"] == body["request_id"]
        assert done["session_id"] == body["session_id"]
        assert isinstance(done.get("generation_id"), str) and done["generation_id"]
        assert isinstance(done.get("draft_id"), int)
        assert isinstance(done.get("final"), dict)
        assert isinstance(done["final"].get("body"), str) and done["final"]["body"].strip()
        assert done["mode"] in {"mock", "real"}
        assert isinstance(done["violation_codes"], list)
        assert isinstance(done["violation_count"], int)
        assert done["enforcement_level"] in {"warn", "repair", "block"}
        assert isinstance(done["repair_loop_enabled"], bool)

        remix = await client.post(
            "/web/v1/remix",
            json={
                "session_id": body["session_id"],
                "style_profile": {
                    "formality": 0.8,
                    "orientation": 0.8,
                    "length": 0.9,
                    "assertiveness": -0.9,
                },
            },
            headers=_headers(),
        )
        assert remix.status_code == 200

        remix_stream = await client.get(f"/web/v1/stream/{remix.json()['request_id']}", headers=_headers())
        assert remix_stream.status_code == 200
        assert "event: done" in remix_stream.text
        remixed = _stream_token_text(remix_stream.text)
        assert "Acme" in remixed
        _assert_upgraded_cta(remixed)
        remix_done = _stream_done_payload(remix_stream.text)
        assert remix_done["request_id"] == remix.json()["request_id"]
        assert remix_done["session_id"] == body["session_id"]
        assert remix_done["generation_id"] != done["generation_id"]

        feedback = await client.post(
            "/web/v1/feedback",
            json={
                "session_id": body["session_id"],
                "draft_before": "Subject: A\nBody:\nBody",
                "draft_after": "Subject: B\nBody:\nBody changed",
                "style_profile": {
                    "formality": 0.0,
                    "orientation": 0.0,
                    "length": 0.0,
                    "assertiveness": 0.0,
                },
            },
            headers=_headers(),
        )
        assert feedback.status_code == 200
        assert feedback.json() == {"ok": True}


@pytest.mark.asyncio
async def test_stream_mid_switch_and_reconnect_prefers_latest_generation():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"
    os.environ["FEATURE_LOSSLESS_STREAMING"] = "1"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start_a = await client.post("/web/v1/generate", json=_generate_payload(), headers=_headers())
        assert start_a.status_code == 200
        a_body = start_a.json()
        stream_a = await client.get(f"/web/v1/stream/{a_body['request_id']}", headers=_headers())
        assert stream_a.status_code == 200
        events_a = _stream_events(stream_a.text)
        done_a = _stream_done_payload(stream_a.text)

        remix = await client.post(
            "/web/v1/remix",
            json={
                "session_id": a_body["session_id"],
                "style_profile": {
                    "formality": 0.8,
                    "orientation": 0.8,
                    "length": 0.9,
                    "assertiveness": -0.9,
                },
            },
            headers=_headers(),
        )
        assert remix.status_code == 200
        stream_b = await client.get(f"/web/v1/stream/{remix.json()['request_id']}", headers=_headers())
        assert stream_b.status_code == 200
        events_b = _stream_events(stream_b.text)
        done_b = _stream_done_payload(stream_b.text)

    # Simulate mid-stream switch + reconnect replay:
    # - start reading generation A
    # - switch to generation B
    # - stale tail from A arrives after reconnect
    mixed_events = events_a[:6] + events_b + events_a[6:]
    active_generation = None
    reconstructed = ""
    final_body = ""
    for event_name, payload in mixed_events:
        generation_id = payload.get("generation_id")
        if event_name == "start" and generation_id:
            active_generation = generation_id
            reconstructed = ""
            continue
        if active_generation and generation_id and generation_id != active_generation:
            continue
        if event_name == "token":
            reconstructed += str(payload.get("token") or "")
        elif event_name == "done" and isinstance(payload.get("final"), dict):
            final_body = str(payload["final"].get("body") or "")

    assert done_a["generation_id"] != done_b["generation_id"]
    assert final_body == done_b["final"]["body"]
    assert reconstructed


@pytest.mark.asyncio
async def test_web_generate_real_mode_json_repair_and_research_containment(monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "0"
    os.environ["EMAILDJ_REAL_PROVIDER"] = "openai"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL"] = "repair"
    os.environ["EMAILDJ_REPAIR_LOOP_ENABLED"] = "1"

    from main import app
    import email_generation.remix_engine as remix_engine

    from email_generation.quick_generate import GenerateResult

    calls = {"count": 0}

    async def fake_real_generate(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] == 1:
            text = "Subject: invalid format\nBody: invalid"
        else:
            text = json.dumps(
                {
                    "subject": "Remix Studio for Acme",
                    "body": (
                        "Hi Alex, Acme recently launched outbound AI initiatives in enterprise accounts and your SDR team "
                        "is under pressure to improve response quality without adding process overhead. "
                        "Remix Studio helps keep messaging specific and controlled while fitting your existing workflow. "
                        "It gives reps clearer guardrails so output quality stays consistent across high-volume outreach "
                        "without introducing extra tooling complexity for managers.\n\n"
                        "Open to a quick chat to see if this is relevant?"
                    ),
                }
            )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=calls["count"])

    monkeypatch.setattr(remix_engine, "_real_generate", fake_real_generate)

    payload = _generate_payload()
    payload["research_text"] = (
        "Acme launched a new enterprise outreach initiative in January. "
        "Outreach should propose a pilot that shows measurable results."
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=payload, headers=_headers())
        assert start.status_code == 200
        body = start.json()
        session = await remix_engine.load_session(body["session_id"])
        assert session is not None
        assert "outreach should" not in session["research_text_sanitized"].lower()
        assert session["allowed_facts"]

        stream = await client.get(f"/web/v1/stream/{body['request_id']}", headers=_headers())
        assert stream.status_code == 200
        generated = _stream_token_text(stream.text)
        assert "Subject:" in generated
        assert "Body:" in generated
        _assert_upgraded_cta(generated)
        assert "pipeline outcomes" not in generated.lower()
        done = _stream_done_payload(stream.text)
        assert done["mode"] == "real"
        assert done["provider"] == "openai"
        assert isinstance(done["model"], str)
        assert done["model"] != "mock"

    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_web_generate_respects_offer_lock_and_blocks_adjacent_products_in_mock_mode():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post(
            "/web/v1/generate",
            json=_generate_payload(
                {
                    "company_name": "EmailDJ",
                    "company_url": "https://emaildj.ai",
                    "current_product": "Remix Studio",
                    "other_products": "Prospect Enrichment, Sequence QA",
                }
            ),
            headers=_headers(),
        )
        assert start.status_code == 200
        body = start.json()

        stream = await client.get(f"/web/v1/stream/{body['request_id']}", headers=_headers())
        assert stream.status_code == 200
        assert "event: done" in stream.text
        rendered = _stream_token_text(stream.text)
        assert "Remix Studio" in rendered
        assert "Prospect Enrichment" not in rendered
        assert "Sequence QA" not in rendered


@pytest.mark.asyncio
async def test_web_generate_rejects_current_product_offer_lock_mismatch():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    payload = _generate_payload(
        {
            "company_name": "EmailDJ",
            "company_url": "https://emaildj.ai",
            "current_product": "Prospect Enrichment",
            "other_products": "Prospect Enrichment, Sequence QA",
        }
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=payload, headers=_headers())
        assert start.status_code == 422
        detail = start.json()["detail"]
        assert detail["error"] == "offer_lock_current_product_mismatch"
        assert detail["offer_lock"] == payload["offer_lock"]
        assert detail["current_product"] == payload["company_context"]["current_product"]


@pytest.mark.asyncio
async def test_web_generate_empty_cta_uses_canonical_fallback():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    payload = _generate_payload()
    payload["cta_offer_lock"] = ""
    payload["cta_type"] = None

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=payload, headers=_headers())
        assert start.status_code == 200
        body = start.json()

        stream = await client.get(f"/web/v1/stream/{body['request_id']}", headers=_headers())
        assert stream.status_code == 200
        rendered = _stream_token_text(stream.text)
        _assert_upgraded_cta(rendered)


@pytest.mark.asyncio
async def test_web_generate_rc_tco_contract_streams_strict_json():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    payload = _generate_payload()
    payload["response_contract"] = "rc_tco_json_v1"
    payload["pipeline_meta"] = {"mode": "generate", "model_hint": "gpt-4.1-nano"}
    payload["cta_offer_lock"] = "Open to a 15-min chat to sanity-check fit? Worth a look / Not a priority?"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=payload, headers=_headers())
        assert start.status_code == 200
        body = start.json()

        stream = await client.get(f"/web/v1/stream/{body['request_id']}", headers=_headers())
        assert stream.status_code == 200
        generated = _stream_token_json(stream.text)
        assert set(generated.keys()) == {
            "user_company_intel",
            "prospect_intel",
            "message_plan",
            "email",
            "self_check",
            "debug",
        }
        assert generated["self_check"]["cta_count"] == 1
        assert generated["self_check"]["cta_is_last_line"] is True
        assert generated["debug"]["effective_model_used"] == "mock"
        done = _stream_done_payload(stream.text)
        assert done["response_contract"] == "rc_tco_json_v1"


@pytest.mark.asyncio
async def test_web_generate_missing_offer_lock_returns_422():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    payload = _generate_payload()
    payload["offer_lock"] = ""

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=payload, headers=_headers())
        assert start.status_code == 422


@pytest.mark.asyncio
async def test_web_beta_key_required_and_rate_limit():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "rate-key-stream"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.post("/web/v1/generate", json=_generate_payload())
        assert unauthorized.status_code == 401

        headers = {"x-emaildj-beta-key": "rate-key-stream"}

        first = await client.post("/web/v1/generate", json=_generate_payload(), headers=headers)
        assert first.status_code == 200

        second = await client.post("/web/v1/generate", json=_generate_payload(), headers=headers)
        assert second.status_code == 429


@pytest.mark.asyncio
async def test_web_stream_get_does_not_consume_post_rate_limit_quota():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "rate-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "1"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        headers = {"x-emaildj-beta-key": "rate-key"}

        first = await client.post("/web/v1/generate", json=_generate_payload(), headers=headers)
        assert first.status_code == 200
        request_id = first.json()["request_id"]

        stream = await client.get(f"/web/v1/stream/{request_id}", headers=headers)
        assert stream.status_code == 200

        second = await client.post("/web/v1/generate", json=_generate_payload(), headers=headers)
        assert second.status_code == 429


@pytest.mark.asyncio
async def test_web_generate_preflight_options_bypasses_beta_key():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        preflight = await client.options(
            "/web/v1/generate",
            headers={
                "Origin": "http://localhost:5174",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-emaildj-beta-key",
            },
        )
        assert preflight.status_code in (200, 204)
        assert preflight.headers.get("access-control-allow-origin") == "http://localhost:5174"


@pytest.mark.asyncio
async def test_web_preview_batch_endpoint_disabled_returns_503():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"
    os.environ["EMAILDJ_PRESET_PREVIEW_PIPELINE"] = "off"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/web/v1/preset-previews/batch", json=_preview_batch_payload(), headers=_headers())
        assert res.status_code == 503
        assert res.json()["detail"]["error"] == "preview_pipeline_disabled"


@pytest.mark.asyncio
async def test_web_preview_batch_endpoint_mock_contract():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["USE_PROVIDER_STUB"] = "1"
    os.environ["EMAILDJ_PRESET_PREVIEW_PIPELINE"] = "on"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/web/v1/preset-previews/batch", json=_preview_batch_payload(), headers=_headers())
        assert res.status_code == 200
        data = res.json()
        assert "previews" in data
        assert len(data["previews"]) == 2
        assert "meta" in data
        assert data["meta"]["provider"] == "mock"
        assert isinstance(data["meta"]["request_id"], str)
        assert data["meta"]["session_id"] is None
        assert isinstance(data["meta"]["violation_codes"], list)
        assert isinstance(data["meta"]["violation_count"], int)
        assert data["meta"]["enforcement_level"] in {"warn", "repair", "block"}
        assert isinstance(data["meta"]["repair_loop_enabled"], bool)

        subjects = {item["subject"] for item in data["previews"]}
        assert len(subjects) == len(data["previews"])

        for item in data["previews"]:
            assert item["preset_id"]
            assert item["label"]
            assert len(item["whyItWorks"]) == 3
            assert 2 <= len(item["vibeTags"]) <= 4
            word_count = len(item["body"].split())
            assert 90 <= word_count <= 130
