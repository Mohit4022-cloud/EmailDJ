"""Quick-generate route set with mock/real mode, TTL cleanup, and concurrency controls."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from api.schemas import QuickGenerateAccepted, QuickGenerateRequest
from context_vault import cache
from email_generation.quick_generate import quick_generate
from email_generation.streaming import stream_response
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()

REQUEST_TTL_SECONDS = int(os.environ.get("QUICK_REQUEST_TTL_SECONDS", "300"))
MAX_CONCURRENT_STREAMS = int(os.environ.get("QUICK_MAX_CONCURRENT_STREAMS", "32"))


@dataclass
class RequestRecord:
    payload: dict
    created_at: float


_REQUESTS: dict[str, RequestRecord] = {}
_STREAM_SEM = asyncio.Semaphore(MAX_CONCURRENT_STREAMS)


def _cleanup_expired() -> None:
    now = time.time()
    expired = [rid for rid, rec in _REQUESTS.items() if now - rec.created_at > REQUEST_TTL_SECONDS]
    for rid in expired:
        del _REQUESTS[rid]


async def _track_cost(account_id: str, request_id: str, input_size: int, output_size: int, throttled: bool) -> None:
    redis = get_redis()
    tier_key = "cost_tier3" if throttled else "cost_tier2"
    estimated = round((input_size / 4000.0) * 0.0002 + (output_size / 2000.0) * 0.0004, 7)
    key = f"{tier_key}:{account_id or 'default'}"
    current_raw = await redis.get(key)
    current = float(current_raw or 0.0)
    await redis.set(key, f"{current + estimated:.7f}")
    logger.info(
        "quick_generate_cost_tracked",
        extra={"request_id": request_id, "account_id": account_id, "tier_key": tier_key, "estimated_cost": estimated},
    )


@router.post("/quick", response_model=QuickGenerateAccepted)
async def start_quick_generate(req: QuickGenerateRequest) -> QuickGenerateAccepted:
    _cleanup_expired()
    request_id = str(uuid4())
    _REQUESTS[request_id] = RequestRecord(payload=req.model_dump(), created_at=time.time())
    return QuickGenerateAccepted(request_id=request_id, stream_url=f"/generate/stream/{request_id}")


@router.get("/stream/{request_id}")
async def stream_quick_generate(request_id: str, request: Request):
    _cleanup_expired()
    rec = _REQUESTS.pop(request_id, None)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "request_id": request_id})

    body = rec.payload["payload"]
    slider_value = rec.payload.get("slider_value", 5)
    account_id = body.get("accountId", "")
    throttled = bool(getattr(request.state, "cost_throttled", False))
    mode = os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock")
    logger.info(
        "quick_generate_stream_start",
        extra={"request_id": request_id, "account_id": account_id, "slider_value": slider_value, "mode": mode, "throttled": throttled},
    )

    account_context = await cache.get_or_fetch(account_id)
    base_gen = quick_generate(
        payload=body,
        account_context=account_context,
        slider_value=slider_value,
        throttled=throttled,
        use_mock=None,
    )

    async def _bounded_and_tracked():
        input_size = len(str(body))
        output_size = 0
        async with _STREAM_SEM:
            async for chunk in base_gen:
                output_size += len(chunk)
                yield chunk
        await _track_cost(account_id=account_id, request_id=request_id, input_size=input_size, output_size=output_size, throttled=throttled)

    return await stream_response(request_id=request_id, generator=_bounded_and_tracked())
