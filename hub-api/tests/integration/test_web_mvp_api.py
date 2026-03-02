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
    }


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
        assert "Acme" in stream.text

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
        assert "Acme" in remix_stream.text

        feedback = await client.post(
            "/web/v1/feedback",
            json={
                "session_id": body["session_id"],
                "draft_before": "Subject: A\n\nBody",
                "draft_after": "Subject: B\n\nBody changed",
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
async def test_web_generate_includes_company_context_mapping_in_mock_mode():
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
        tokens: list[str] = []
        for line in stream.text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[6:])
            token = payload.get("token")
            if token:
                tokens.append(token)
        assert "Remix Studio" in "".join(tokens)


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

        subjects = {item["subject"] for item in data["previews"]}
        assert len(subjects) == len(data["previews"])

        for item in data["previews"]:
            assert item["preset_id"]
            assert item["label"]
            assert len(item["whyItWorks"]) == 3
            assert 2 <= len(item["vibeTags"]) <= 4
            word_count = len(item["body"].split())
            assert 90 <= word_count <= 130
