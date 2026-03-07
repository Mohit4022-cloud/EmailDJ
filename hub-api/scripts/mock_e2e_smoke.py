"""Mock E2E smoke: ingest -> generate -> stream done."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
os.environ.setdefault("USE_PROVIDER_STUB", "1")
os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")

import httpx
from main import app


async def run() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "payload": {
                "accountId": "001-test",
                "accountName": "Acme",
                "industry": "SaaS",
                "notes": ["Budget is $200k in Q2"],
                "activityTimeline": [],
            }
        }

        ing = await client.post("/vault/ingest", json=payload)
        ing.raise_for_status()

        start = await client.post("/generate/quick", json={"payload": payload["payload"], "slider_value": 5})
        start.raise_for_status()
        request_id = start.json()["request_id"]

        stream = await client.get(f"/generate/stream/{request_id}")
        stream.raise_for_status()
        text = stream.text
        assert "event: done" in text, "missing done event"


if __name__ == "__main__":
    asyncio.run(run())
    print("mock e2e smoke passed")
