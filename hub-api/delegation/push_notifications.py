"""Assignment notification signals."""

from __future__ import annotations

from infra.redis_client import get_redis


async def notify_sdr(sdr_id: str, assignment_summary: dict) -> None:
    redis = get_redis()
    await redis.setex(f"new_assignments_flag:{sdr_id}", 3600, "1")
