"""
Campaigns route — VP Campaign Builder endpoints.

IMPLEMENTATION INSTRUCTIONS:
Endpoints:
  POST /campaigns                    → VP creates a campaign
  GET  /campaigns/{id}               → get campaign details + status
  POST /campaigns/{id}/approve       → VP approves audience (human gate)
  POST /campaigns/{id}/assign        → VP assigns to SDR(s)

POST /campaigns logic:
1. Parse VP command from request body: { command: str, campaign_name: str }.
2. Kick off LangGraph pipeline: call build_vp_campaign_graph() from agents/graph.py.
3. Invoke graph with initial state: AgentState(vp_command=command).
4. Graph runs: intent_classifier → crm_query_agent → intent_data_agent →
   audience_builder → [HUMAN INTERRUPT] → sequence_drafter.
5. Graph pauses at human_review interrupt after audience_builder.
6. Store campaign in DB with status='awaiting_approval', save graph checkpoint thread_id.
7. Return { campaign_id, status: 'awaiting_approval', estimated_audience_size }.

POST /campaigns/{id}/approve logic:
1. Load campaign from DB. Verify VP identity from auth.
2. If audience count > BLAST_RADIUS_CONFIRM_THRESHOLD (default 200):
   - Require request body to contain { confirm: "CONFIRM" } (exact string).
   - If not present, return 400 with { error: 'blast_radius_confirmation_required',
     audience_count, threshold }.
3. Resume LangGraph graph from checkpoint (thread_id) — this triggers sequence_drafter.
4. Update campaign status to 'drafting'.

POST /campaigns/{id}/assign logic:
1. Verify campaign status is 'sequences_ready'.
2. Parse { sdr_ids: list[str] } from request body.
3. Call delegation.engine.create_assignment() for each SDR.
4. Update campaign status to 'assigned'.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/campaigns")
async def create_campaign():
    # TODO: implement per instructions above
    pass


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    # TODO: implement per instructions above
    pass


@router.post("/campaigns/{campaign_id}/approve")
async def approve_campaign(campaign_id: str):
    # TODO: implement per instructions above
    pass


@router.post("/campaigns/{campaign_id}/assign")
async def assign_campaign(campaign_id: str):
    # TODO: implement per instructions above
    pass
