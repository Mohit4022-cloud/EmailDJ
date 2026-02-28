"""Async deep-research job endpoints."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.nodes.deep_research_agent import deep_research_agent_node

router = APIRouter()
_JOBS: dict[str, dict] = {}


class DeepResearchRequest(BaseModel):
    account_id: str
    domain: str
    company_name: str


async def _run_job(job_id: str, req: DeepResearchRequest) -> None:
    _JOBS[job_id]["status"] = "running"
    state = await deep_research_agent_node({"vp_command": req.company_name})
    _JOBS[job_id]["status"] = "complete"
    _JOBS[job_id]["result"] = state.get("research")


@router.post("/")
async def start_research(req: DeepResearchRequest):
    job_id = str(uuid4())
    _JOBS[job_id] = {
        "status": "queued",
        "account_id": req.account_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "progress": 0,
    }
    asyncio.create_task(_run_job(job_id, req))
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}/status")
async def get_research_status(job_id: str):
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "not_found", "job_id": job_id})
    return job
