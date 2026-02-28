"""Embedding generation and storage."""

from __future__ import annotations

from context_vault.models import AccountContext
from infra import vector_store


async def embed_and_store(context: AccountContext, account_id: str) -> None:
    summary = (
        f"Account: {context.account_name or account_id}; "
        f"Industry: {context.industry or 'unknown'}; "
        f"Employees: {context.employee_count or 0}; "
        f"Status: {context.contract_status or 'unknown'}"
    )
    # Deterministic, local-dev friendly pseudo-embedding.
    embedding = [float((ord(ch) % 53) / 53.0) for ch in summary[:128]]
    if len(embedding) < 128:
        embedding.extend([0.0] * (128 - len(embedding)))
    await vector_store.upsert(
        account_id=account_id,
        embedding=embedding,
        metadata={
            "account_id": account_id,
            "domain": context.domain,
            "industry": context.industry,
            "freshness": context.freshness,
        },
    )
