"""Delegation queue implementation backed by Redis."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4

from infra.redis_client import get_redis


@dataclass
class AssignmentSummary:
    id: str
    campaign_name: str
    vp_name: str
    account_count: int
    rationale_snippet: str
    created_at: str
    status: str = "pending"


async def _save_assignment_row(assignment_id: str, row: dict) -> None:
    redis = get_redis()
    await redis.hset(f"assignment:{assignment_id}", mapping={"data": json.dumps(row)})


async def _load_assignment_row(assignment_id: str) -> dict | None:
    redis = get_redis()
    raw = await redis.hget(f"assignment:{assignment_id}", "data")
    if not raw:
        return None
    return json.loads(raw)


async def create_assignment(campaign_id: str, sdr_id: str, accounts: list, *, campaign_name: str = "Campaign", vp_name: str = "VP", rationale: str = "") -> str:
    assignment_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    data = {
        "id": assignment_id,
        "campaign_id": campaign_id,
        "sdr_id": sdr_id,
        "accounts": accounts,
        "status": "pending",
        "campaign_name": campaign_name,
        "vp_name": vp_name,
        "rationale": rationale,
        "created_at": created_at,
        "sent_at": None,
    }

    await _save_assignment_row(assignment_id, data)

    redis = get_redis()
    await redis.sadd(f"sdr_assignments:{sdr_id}", assignment_id)
    return assignment_id


async def get_pending_assignments(sdr_id: str) -> list[AssignmentSummary]:
    redis = get_redis()
    ids = await redis.smembers(f"sdr_assignments:{sdr_id}")
    out: list[AssignmentSummary] = []
    for assignment_id in ids:
        row = await _load_assignment_row(assignment_id)
        if not row or row.get("status") != "pending":
            continue
        out.append(
            AssignmentSummary(
                id=row["id"],
                campaign_name=row.get("campaign_name", "Campaign"),
                vp_name=row.get("vp_name", "VP"),
                account_count=len(row.get("accounts", [])),
                rationale_snippet=(row.get("rationale") or "")[:140],
                created_at=row.get("created_at"),
                status=row.get("status", "pending"),
            )
        )
    return out


async def mark_sent(assignment_id: str, email_draft: str, final_edit: str) -> None:
    row = await _load_assignment_row(assignment_id)
    if not row:
        return
    row["status"] = "sent"
    row["sent_at"] = datetime.now(timezone.utc).isoformat()
    row["email_draft"] = email_draft
    row["final_edit"] = final_edit
    await _save_assignment_row(assignment_id, row)

    redis = get_redis()
    await redis.srem(f"sdr_assignments:{row['sdr_id']}", assignment_id)


async def get_assignment(assignment_id: str) -> dict | None:
    return await _load_assignment_row(assignment_id)


async def set_assignment_status(assignment_id: str, status: str) -> bool:
    row = await _load_assignment_row(assignment_id)
    if not row:
        return False
    row["status"] = status
    await _save_assignment_row(assignment_id, row)
    return True


def serialize_summary(summary: AssignmentSummary) -> dict:
    return asdict(summary)
