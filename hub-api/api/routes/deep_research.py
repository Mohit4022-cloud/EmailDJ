"""
Deep Research route — async long-running research pipeline.

IMPLEMENTATION INSTRUCTIONS:
Endpoints:
  POST /research       → enqueue research job, return { job_id: str }
  GET  /research/{job_id}/status → return { status, progress, result? }

Logic for POST /research:
1. Validate request: requires account_id, domain, company_name.
2. Check rate limit: `deep_research_rate:{account_id}` in Redis using sliding
   window counter. Limit: 200 per hour (from env DEEP_RESEARCH_RATE_LIMIT_PER_HOUR).
3. For >50 simultaneous requests queued: batch in groups of 50 with 5-minute
   intervals. Return estimated wait time in response.
4. Generate a unique job_id (uuid4). Store job state in Redis:
   `research_job:{job_id}` = { status: 'queued', account_id, created_at }
5. Use FastAPI BackgroundTasks to enqueue deep_research_agent_node execution.
6. The background task: run the deep_research_agent_node, update job state to
   'running' then 'complete'|'failed' in Redis.
7. On completion, store result in Context Vault.

Logic for GET /research/{job_id}/status:
1. Fetch `research_job:{job_id}` from Redis.
2. Return status + partial result if available.
3. If job_id not found, return 404.
"""

from fastapi import APIRouter

router = APIRouter()


@router.post("/research")
async def start_research():
    # TODO: implement per instructions above
    pass


@router.get("/research/{job_id}/status")
async def get_research_status(job_id: str):
    # TODO: implement per instructions above
    pass
