import os
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))


def _headers():
    return {"x-emaildj-beta-key": "test-key"}


def _generate_payload():
    return {
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
