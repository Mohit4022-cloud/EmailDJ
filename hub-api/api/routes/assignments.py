"""Assignment polling/accept endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response

from delegation import engine

router = APIRouter()


@router.get("/poll")
async def poll_assignments(response: Response, sdr_id: str = "demo-sdr"):
    summaries = await engine.get_pending_assignments(sdr_id=sdr_id)
    response.headers["Cache-Control"] = "no-cache"
    return {
        "count": len(summaries),
        "assignments": [engine.serialize_summary(s) for s in summaries],
    }


@router.post("/{assignment_id}/accept")
async def accept_assignment(assignment_id: str):
    ok = await engine.set_assignment_status(assignment_id, "in-review")
    if not ok:
        return {"status": "not_found", "assignment_id": assignment_id}
    return {"status": "ok", "assignment_id": assignment_id}
