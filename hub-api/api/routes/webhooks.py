"""Webhook endpoints for edit/send/reply signals."""

from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter

from api.schemas import WebhookEditRequest, WebhookReplyRequest, WebhookSendRequest
from delegation import engine
from infra.redis_client import get_redis

router = APIRouter()


def _signal_ids_key(kind: str) -> str:
    return f"webhook_signals:{kind}:ids"


def _signal_row_key(kind: str, row_id: str) -> str:
    return f"webhook_signal:{kind}:{row_id}"


async def _append_signal(kind: str, payload: dict) -> str:
    row_id = str(uuid4())
    redis = get_redis()
    await redis.hset(_signal_row_key(kind, row_id), mapping={"data": json.dumps(payload)})
    await redis.sadd(_signal_ids_key(kind), row_id)
    return row_id


async def _load_signals(kind: str, limit: int = 100) -> list[dict]:
    redis = get_redis()
    ids = sorted(await redis.smembers(_signal_ids_key(kind)))
    if limit > 0:
        ids = ids[-limit:]

    out: list[dict] = []
    for row_id in ids:
        raw = await redis.hget(_signal_row_key(kind, row_id), "data")
        if raw:
            out.append(json.loads(raw))
    return out


@router.post("/edit")
async def capture_edit(req: WebhookEditRequest):
    diff = list(difflib.ndiff(req.original_draft.splitlines(), req.final_edit.splitlines()))
    diff_size_chars = abs(len(req.final_edit) - len(req.original_draft))
    major = len(req.final_edit) > 0 and diff_size_chars / max(len(req.original_draft), 1) > 0.3

    await _append_signal(
        "edit",
        {
            "assignment_id": req.assignment_id,
            "account_id": req.account_id,
            "original_draft": req.original_draft,
            "final_edit": req.final_edit,
            "diff": diff,
            "prompt_evolution_flag": major,
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"status": "captured", "diff_size_chars": diff_size_chars}


@router.post("/send")
async def capture_send(req: WebhookSendRequest):
    final_edit = req.final_edit or req.email_draft
    await engine.mark_sent(req.assignment_id, req.email_draft, final_edit)
    await _append_signal(
        "send",
        {
            "assignment_id": req.assignment_id,
            "account_id": req.account_id,
            "sent_at": (req.sent_at or datetime.now(timezone.utc)).isoformat(),
        },
    )
    return {"status": "ok"}


@router.post("/reply")
async def capture_reply(req: WebhookReplyRequest):
    await _append_signal("reply", req.model_dump(mode="json"))
    return {"status": "ok"}
