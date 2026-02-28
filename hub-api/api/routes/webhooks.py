"""Webhook endpoints for edit/send/reply signals."""

from __future__ import annotations

import difflib
from datetime import datetime, timezone

from fastapi import APIRouter

from api.schemas import WebhookEditRequest, WebhookReplyRequest, WebhookSendRequest
from delegation import engine

router = APIRouter()

_EDIT_SIGNALS: list[dict] = []
_SEND_SIGNALS: list[dict] = []
_REPLY_SIGNALS: list[dict] = []


@router.post("/edit")
async def capture_edit(req: WebhookEditRequest):
    diff = list(difflib.ndiff(req.original_draft.splitlines(), req.final_edit.splitlines()))
    diff_size_chars = abs(len(req.final_edit) - len(req.original_draft))
    major = len(req.final_edit) > 0 and diff_size_chars / max(len(req.original_draft), 1) > 0.3

    _EDIT_SIGNALS.append(
        {
            "assignment_id": req.assignment_id,
            "account_id": req.account_id,
            "original_draft": req.original_draft,
            "final_edit": req.final_edit,
            "diff": diff,
            "prompt_evolution_flag": major,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return {"status": "captured", "diff_size_chars": diff_size_chars}


@router.post("/send")
async def capture_send(req: WebhookSendRequest):
    final_edit = req.final_edit or req.email_draft
    await engine.mark_sent(req.assignment_id, req.email_draft, final_edit)
    _SEND_SIGNALS.append(
        {
            "assignment_id": req.assignment_id,
            "account_id": req.account_id,
            "sent_at": (req.sent_at or datetime.now(timezone.utc)).isoformat(),
        }
    )
    return {"status": "ok"}


@router.post("/reply")
async def capture_reply(req: WebhookReplyRequest):
    _REPLY_SIGNALS.append(req.model_dump())
    return {"status": "ok"}
