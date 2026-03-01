"""Web MVP routes for generate/remix/feedback workflows."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from api.schemas import (
    WebFeedbackRequest,
    WebGenerateAccepted,
    WebGenerateRequest,
    WebRemixAccepted,
    WebRemixRequest,
)
from email_generation.remix_engine import build_draft, create_session_payload, load_session, save_session
from email_generation.streaming import stream_response
from infra.redis_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter()
_STREAM_SEM = asyncio.Semaphore(32)
_REQUEST_TTL_SECONDS = 5 * 60


@dataclass
class RequestRecord:
    session_id: str
    style_profile: dict
    mode: str
    created_at: float


_REQUESTS: dict[str, RequestRecord] = {}


def _cleanup_expired() -> None:
    now = time.time()
    expired = [rid for rid, rec in _REQUESTS.items() if now - rec.created_at > _REQUEST_TTL_SECONDS]
    for rid in expired:
        del _REQUESTS[rid]


def _day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


async def _emit_metric(name: str) -> None:
    redis = get_redis()
    key = f"web_mvp:metric:{_day_key()}:{name}"
    await redis.incr(key)
    await redis.expire(key, 3 * 24 * 60 * 60)


def _token_stream(text: str):
    async def _gen():
        words = text.split(" ")
        first = True
        for token in words:
            if first:
                await asyncio.sleep(0.01)
                first = False
            else:
                await asyncio.sleep(0.005)
            yield token + " "

    return _gen()


@router.post("/generate", response_model=WebGenerateAccepted)
async def web_generate(req: WebGenerateRequest) -> WebGenerateAccepted:
    _cleanup_expired()
    await _emit_metric("web_generate_started")

    session_id = str(uuid4())
    session = create_session_payload(
        prospect=req.prospect.model_dump(),
        research_text=req.research_text,
        initial_style=req.style_profile.model_dump(),
    )
    await save_session(session_id, session)

    request_id = str(uuid4())
    _REQUESTS[request_id] = RequestRecord(
        session_id=session_id,
        style_profile=req.style_profile.model_dump(),
        mode="generate",
        created_at=time.time(),
    )
    return WebGenerateAccepted(request_id=request_id, session_id=session_id, stream_url=f"/web/v1/stream/{request_id}")


@router.post("/remix", response_model=WebRemixAccepted)
async def web_remix(req: WebRemixRequest) -> WebRemixAccepted:
    _cleanup_expired()
    session = await load_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": req.session_id})

    await _emit_metric("web_remix_started")
    request_id = str(uuid4())
    _REQUESTS[request_id] = RequestRecord(
        session_id=req.session_id,
        style_profile=req.style_profile.model_dump(),
        mode="remix",
        created_at=time.time(),
    )
    return WebRemixAccepted(request_id=request_id, stream_url=f"/web/v1/stream/{request_id}")


@router.get("/stream/{request_id}")
async def web_stream(request_id: str, request: Request):
    _cleanup_expired()
    rec = _REQUESTS.pop(request_id, None)
    if rec is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "request_id": request_id})

    session = await load_session(rec.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": rec.session_id})

    throttled = bool(getattr(request.state, "cost_throttled", False))
    start = time.perf_counter()

    async def _bounded():
        async with _STREAM_SEM:
            result = await build_draft(session=session, style_profile=rec.style_profile, throttled=throttled)
            async for token in _token_stream(result.draft):
                yield token
            if rec.mode == "generate":
                session["metrics"]["generate_count"] = int(session["metrics"].get("generate_count", 0)) + 1
                await _emit_metric("web_generate_completed")
            else:
                session["metrics"]["remix_count"] = int(session["metrics"].get("remix_count", 0)) + 1
                await _emit_metric("web_remix_completed")
            session["metrics"]["last_latency_ms"] = int((time.perf_counter() - start) * 1000)
            await save_session(rec.session_id, session)
            logger.info(
                "web_mvp_stream_done",
                extra={
                    "mode": rec.mode,
                    "session_id": rec.session_id,
                    "request_id": request_id,
                    "latency_ms": session["metrics"]["last_latency_ms"],
                },
            )

    return await stream_response(request_id=request_id, generator=_bounded())


@router.post("/feedback")
async def web_feedback(req: WebFeedbackRequest):
    session = await load_session(req.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"error": "session_not_found", "session_id": req.session_id})

    redis = get_redis()
    key = f"web_mvp:feedback:{req.session_id}:{int(time.time())}"
    await redis.hset(
        key,
        mapping={
            "draft_before": req.draft_before,
            "draft_after": req.draft_after,
            "style_profile": json.dumps(req.style_profile.model_dump()),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await redis.expire(key, 7 * 24 * 60 * 60)
    await _emit_metric("web_copy_clicked")
    return {"ok": True}
