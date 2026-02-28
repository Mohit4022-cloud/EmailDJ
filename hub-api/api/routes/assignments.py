"""
Assignments route — Delegation Engine pull endpoint for SDRs.

IMPLEMENTATION INSTRUCTIONS:
Endpoint: GET /assignments
Query params: sdr_id (or inferred from auth token)
Response: { count: int, summary: list[AssignmentSummary] }

Design rationale: MV3 service workers cannot maintain persistent connections.
The Side Panel polls this endpoint every 30 seconds. This endpoint MUST be
lightweight — no full payload, no DB joins for email content.

Logic:
1. Extract sdr_id from auth token (or query param for dev).
2. Call delegation.engine.get_pending_assignments(sdr_id).
3. Return count + summary only:
   { count: int, assignments: [{ id, campaign_name, vp_name, account_count,
     rationale_snippet: str (first 140 chars of VP's rationale), created_at }] }
4. Full campaign payload (pre-drafted emails) is fetched separately via
   GET /campaigns/{id} when the SDR clicks an assignment — NOT here.
5. Add Cache-Control: no-cache header (polling endpoint, always fresh).
6. Target response time: <100ms (Redis-backed, no LLM calls).
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/assignments")
async def get_assignments():
    # TODO: implement per instructions above
    pass
