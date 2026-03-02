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
        "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
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


def _stream_done_payload(stream_text: str) -> dict:
    event_name = ""
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip()
            continue
        if line.startswith("data: ") and event_name == "done":
            return json.loads(line[6:])
    return {}


@pytest.mark.asyncio
async def test_web_generate_and_remix_stream_flow():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

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
        generated = _stream_token_text(stream.text)
        assert "Acme" in generated
        assert "Open to a quick chat to see if this is relevant?" in generated
        assert "Subject:" in generated
        assert "Body:" in generated
        done = _stream_done_payload(stream.text)
        assert done["request_id"] == body["request_id"]
        assert done["session_id"] == body["session_id"]
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
        assert "Open to a quick chat to see if this is relevant?" in remixed
        remix_done = _stream_done_payload(remix_stream.text)
        assert remix_done["request_id"] == remix.json()["request_id"]
        assert remix_done["session_id"] == body["session_id"]

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
async def test_web_generate_real_mode_json_repair_and_research_containment(monkeypatch):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "real"
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
        assert "Open to a quick chat to see if this is relevant?" in generated
        assert "pipeline outcomes" not in generated.lower()

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
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

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
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

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
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

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
        assert "Open to a quick chat to see if this is relevant?" in rendered


@pytest.mark.asyncio
async def test_web_generate_missing_offer_lock_returns_422():
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "30"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

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
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "rate-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "1"
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unauthorized = await client.post("/web/v1/generate", json=_generate_payload())
        assert unauthorized.status_code == 401

        headers = {"x-emaildj-beta-key": "rate-key"}

        first = await client.post("/web/v1/generate", json=_generate_payload(), headers=headers)
        assert first.status_code == 200

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
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"

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
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"
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
    os.environ["EMAILDJ_QUICK_GENERATE_MODE"] = "mock"
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
