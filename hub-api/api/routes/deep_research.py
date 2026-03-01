"""Async deep-research job endpoints."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.nodes.deep_research_agent import deep_research_agent_node
from infra.redis_client import get_redis

router = APIRouter()


def _jobs_ttl_seconds() -> int:
    raw = os.environ.get("DEEP_RESEARCH_JOB_TTL_SECONDS", "86400").strip()
    try:
        ttl = int(raw)
    except ValueError:
        return 86400
    return ttl if ttl > 0 else 86400


def _job_key(job_id: str) -> str:
    return f"deep_research:job:{job_id}"


async def _save_job(job_id: str, payload: dict) -> None:
    redis = get_redis()
    key = _job_key(job_id)
    await redis.hset(key, mapping={"data": json.dumps(payload)})
    await redis.expire(key, _jobs_ttl_seconds())


async def _load_job(job_id: str) -> dict | None:
    redis = get_redis()
    raw = await redis.hget(_job_key(job_id), "data")
    if not raw:
        return None
    return json.loads(raw)


class DeepResearchRequest(BaseModel):
    account_id: str
    domain: str
    company_name: str


async def _run_job(job_id: str, req: DeepResearchRequest) -> None:
    job = await _load_job(job_id)
    if not job:
        return
    job["status"] = "running"
    job["progress"] = 40
    await _save_job(job_id, job)

    state = await deep_research_agent_node({"vp_command": req.company_name})

    job = await _load_job(job_id) or {"job_id": job_id}
    job["status"] = "complete"
    job["progress"] = 100
    job["result"] = state.get("research")
    await _save_job(job_id, job)


@router.post("/")
async def start_research(req: DeepResearchRequest):
    job_id = str(uuid4())
    job = {
        "job_id": job_id,
        "status": "queued",
        "account_id": req.account_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "progress": 0,
    }
    await _save_job(job_id, job)
    asyncio.create_task(_run_job(job_id, req))
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}/status")
async def get_research_status(job_id: str):
    job = await _load_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail={"error": "not_found", "job_id": job_id})
    return job
