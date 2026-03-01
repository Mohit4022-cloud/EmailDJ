"""Print daily Web MVP metrics from Redis."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from infra.redis_client import get_redis

METRICS = [
    "web_generate_started",
    "web_generate_completed",
    "web_remix_started",
    "web_remix_completed",
    "web_copy_clicked",
]


async def main() -> None:
    redis = get_redis()
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    print(f"Web MVP metrics for UTC day {day}")
    for metric in METRICS:
        key = f"web_mvp:metric:{day}:{metric}"
        value = await redis.get(key)
        print(f"- {metric}: {int(value or 0)}")


if __name__ == "__main__":
    asyncio.run(main())
