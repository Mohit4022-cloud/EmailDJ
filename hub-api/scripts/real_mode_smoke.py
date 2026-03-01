"""Real-mode smoke test for quick-generate contract path."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
os.environ.setdefault("EMAILDJ_QUICK_GENERATE_MODE", "real")
os.environ.setdefault("EMAILDJ_REAL_PROVIDER", "openai")
os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")

import httpx
from main import app


async def run() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "payload": {
                "accountId": "001-real",
                "accountName": "Acme Real",
                "industry": "SaaS",
                "notes": ["Reach me at test@example.com"],
                "activityTimeline": [],
            },
            "slider_value": 5,
        }

        start = await client.post("/generate/quick", json=payload)
        start.raise_for_status()
        request_id = start.json()["request_id"]

        stream = await client.get(f"/generate/stream/{request_id}")
        stream.raise_for_status()
        text = stream.text
        assert "event: start" in text
        assert "event: done" in text


if __name__ == "__main__":
    asyncio.run(run())
    print("real mode smoke passed")
