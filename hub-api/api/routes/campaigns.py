"""Campaign creation, approval, and assignment endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from agents.graph import build_vp_campaign_graph
from delegation import engine, push_notifications
from infra.redis_client import get_redis

router = APIRouter()

BLAST_RADIUS_CONFIRM_THRESHOLD = 200
APPROVER_ROLES = {"vp", "admin"}
_CAMPAIGNS: dict[str, dict] = {}


class CampaignCreateRequest(BaseModel):
    command: str
    campaign_name: str


class CampaignApproveRequest(BaseModel):
    confirm: str | None = None
    approval_reason: str


class CampaignAssignRequest(BaseModel):
    sdr_ids: list[str] = Field(min_length=1)


async def _save_campaign(campaign: dict) -> None:
    _CAMPAIGNS[campaign["id"]] = campaign
    redis = get_redis()
    await redis.hset(f"campaign:{campaign['id']}", mapping={"data": json.dumps(campaign)})


async def _load_campaign(campaign_id: str) -> dict | None:
    # Primary path: Redis-backed campaign state.
    redis = get_redis()
    raw = await redis.hget(f"campaign:{campaign_id}", "data")
    if raw:
        data = json.loads(raw)
        _CAMPAIGNS[campaign_id] = data
        return data

    # Secondary fallback: in-process cache.
    if campaign_id in _CAMPAIGNS:
        return _CAMPAIGNS[campaign_id]
    return None


def _approval_ids_key(campaign_id: str) -> str:
    return f"campaign_approvals:{campaign_id}:ids"


def _approval_row_key(campaign_id: str, approval_id: str) -> str:
    return f"campaign_approval:{campaign_id}:{approval_id}"


def _extract_approver(request: Request) -> tuple[str, str]:
    approver_id = request.headers.get("x-user-id", "").strip()
    approver_role = request.headers.get("x-user-role", "").strip().lower()
    if not approver_id or not approver_role:
        raise HTTPException(status_code=401, detail={"error": "approver_auth_required"})
    if approver_role not in APPROVER_ROLES:
        raise HTTPException(
            status_code=403,
            detail={"error": "approver_forbidden", "required_roles": sorted(APPROVER_ROLES)},
        )
    return approver_id, approver_role


def _campaign_signature(campaign: dict) -> str:
    canonical = {
        "audience": campaign.get("audience", []),
        "sequences": campaign.get("sequences", {}),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _save_approval_record(campaign_id: str, record: dict) -> None:
    approval_id = record["approval_id"]
    redis = get_redis()
    await redis.hset(_approval_row_key(campaign_id, approval_id), mapping={"data": json.dumps(record)})
    await redis.sadd(_approval_ids_key(campaign_id), approval_id)


async def _load_approval_record(campaign_id: str, approval_id: str) -> dict | None:
    redis = get_redis()
    raw = await redis.hget(_approval_row_key(campaign_id, approval_id), "data")
    if not raw:
        return None
    return json.loads(raw)


async def _load_latest_approval(campaign_id: str, latest_approval_id: str | None = None) -> dict | None:
    if latest_approval_id:
        direct = await _load_approval_record(campaign_id, latest_approval_id)
        if direct:
            return direct

    redis = get_redis()
    ids = await redis.smembers(_approval_ids_key(campaign_id))
    latest: dict | None = None
    for approval_id in ids:
        row = await _load_approval_record(campaign_id, approval_id)
        if not row:
            continue
        if latest is None or row.get("approved_at", "") > latest.get("approved_at", ""):
            latest = row
    return latest


def _is_latest_approval_valid(campaign: dict, approval: dict) -> bool:
    latest_id = campaign.get("latest_approval_id")
    if latest_id and approval.get("approval_id") != latest_id:
        return False
    return approval.get("campaign_signature") == _campaign_signature(campaign)


@router.post("/")
async def create_campaign(req: CampaignCreateRequest):
    campaign_id = str(uuid4())
    graph = build_vp_campaign_graph()
    state = await graph.ainvoke({"vp_command": req.command, "errors": []})

    campaign = {
        "id": campaign_id,
        "name": req.campaign_name,
        "vp_command": req.command,
        "status": "awaiting_approval",
        "audience": state.get("audience", []),
        "sequences": state.get("sequences", {}),
        "latest_approval_id": None,
        "latest_approval_signature": None,
        "latest_approved_at": None,
        "thread_id": str(uuid4()),
    }
    await _save_campaign(campaign)
    return {
        "campaign_id": campaign_id,
        "status": campaign["status"],
        "estimated_audience_size": len(campaign["audience"]),
    }


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    campaign = await _load_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    return campaign


@router.post("/{campaign_id}/approve")
async def approve_campaign(campaign_id: str, req: CampaignApproveRequest, request: Request):
    campaign = await _load_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

    approver_id, approver_role = _extract_approver(request)
    audience_count = len(campaign.get("audience", []))
    if audience_count > BLAST_RADIUS_CONFIRM_THRESHOLD and req.confirm != "CONFIRM":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "blast_radius_confirmation_required",
                "audience_count": audience_count,
                "threshold": BLAST_RADIUS_CONFIRM_THRESHOLD,
            },
        )
    approval_reason = (req.approval_reason or "").strip()
    if not approval_reason:
        raise HTTPException(status_code=400, detail={"error": "approval_reason_required"})

    approval_id = str(uuid4())
    approved_at = datetime.now(timezone.utc).isoformat()
    signature = _campaign_signature(campaign)
    await _save_approval_record(
        campaign_id,
        {
            "approval_id": approval_id,
            "campaign_id": campaign_id,
            "approver_id": approver_id,
            "approver_role": approver_role,
            "approved_at": approved_at,
            "audience_count": audience_count,
            "approval_reason": approval_reason,
            "campaign_signature": signature,
        },
    )
    campaign["status"] = "sequences_ready"
    campaign["latest_approval_id"] = approval_id
    campaign["latest_approval_signature"] = signature
    campaign["latest_approved_at"] = approved_at
    await _save_campaign(campaign)
    return {
        "status": campaign["status"],
        "campaign_id": campaign_id,
        "approval_id": approval_id,
        "approved_at": approved_at,
    }


@router.post("/{campaign_id}/assign")
async def assign_campaign(campaign_id: str, req: CampaignAssignRequest):
    campaign = await _load_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if campaign.get("status") != "sequences_ready":
        raise HTTPException(status_code=400, detail={"error": "campaign_not_ready"})
    latest = await _load_latest_approval(campaign_id, campaign.get("latest_approval_id"))
    if not latest:
        raise HTTPException(status_code=400, detail={"error": "approval_required"})
    if not _is_latest_approval_valid(campaign, latest):
        raise HTTPException(
            status_code=400,
            detail={"error": "approval_invalidated", "reason": "campaign_changed_since_approval"},
        )

    created = []
    accounts = campaign.get("audience", [])
    for sdr_id in req.sdr_ids:
        assignment_id = await engine.create_assignment(
            campaign_id=campaign_id,
            sdr_id=sdr_id,
            accounts=accounts,
            campaign_name=campaign.get("name", "Campaign"),
            vp_name="VP",
            rationale=campaign.get("vp_command", ""),
        )
        created.append(assignment_id)
        await push_notifications.notify_sdr(sdr_id, {"assignment_id": assignment_id})

    campaign["status"] = "assigned"
    campaign["assignment_ids"] = created
    await _save_campaign(campaign)
    return {"status": "assigned", "assignment_ids": created}
