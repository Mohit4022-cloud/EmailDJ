"""Context vault endpoints for ingest, retrieval, and cache management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import ProspectPayload, VaultIngestRequest, VaultPrefetchRequest
from context_vault import cache, extractor
from context_vault.models import AccountContext

router = APIRouter()


async def _payload_to_context(payload: ProspectPayload) -> AccountContext:
    notes_text = "\n".join(payload.notes + payload.activityTimeline)
    context = await extractor.extract(raw_notes=notes_text, account_id=payload.accountId)
    if payload.accountName:
        context.account_name = payload.accountName
    context.domain = payload.extractionMetadata.salesforceUrl if payload.extractionMetadata else context.domain
    context.industry = payload.industry or context.industry
    context.employee_count = payload.employeeCount or context.employee_count
    return context


@router.post("/ingest")
async def ingest_context(req: VaultIngestRequest):
    context = await _payload_to_context(req.payload)
    await cache.set(req.payload.accountId, context)
    return {"status": "ok", "account_id": req.payload.accountId, "freshness": context.freshness}


@router.get("/context/{prospect_id}")
async def get_context(prospect_id: str):
    context = await cache.get_or_fetch(prospect_id)
    if context is None:
        raise HTTPException(status_code=404, detail={"error": "not_found", "message": "No context found"})
    return {"account_id": prospect_id, "context": context.model_dump()}


@router.post("/context/{prospect_id}/invalidate")
async def invalidate_context(prospect_id: str):
    await cache.invalidate(prospect_id)
    return {"status": "ok", "account_id": prospect_id}


@router.post("/prefetch")
async def prefetch_contexts(req: VaultPrefetchRequest):
    found = 0
    for account_id in req.account_ids:
        context = await cache.get_or_fetch(account_id)
        if context is not None:
            found += 1
    return {"requested": len(req.account_ids), "found": found}
