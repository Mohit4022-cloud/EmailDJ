"""Campaign creation, approval, and assignment endpoints."""

from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from agents.graph import build_vp_campaign_graph
from delegation import engine, push_notifications
from infra.redis_client import get_redis

router = APIRouter()

BLAST_RADIUS_CONFIRM_THRESHOLD = 200
_CAMPAIGNS: dict[str, dict] = {}


class CampaignCreateRequest(BaseModel):
    command: str
    campaign_name: str


class CampaignApproveRequest(BaseModel):
    confirm: str | None = None


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
async def approve_campaign(campaign_id: str, req: CampaignApproveRequest):
    campaign = await _load_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail={"error": "not_found"})

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

    campaign["status"] = "sequences_ready"
    await _save_campaign(campaign)
    return {"status": campaign["status"], "campaign_id": campaign_id}


@router.post("/{campaign_id}/assign")
async def assign_campaign(campaign_id: str, req: CampaignAssignRequest):
    campaign = await _load_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    if campaign.get("status") != "sequences_ready":
        raise HTTPException(status_code=400, detail={"error": "campaign_not_ready"})

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
