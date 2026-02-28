"""Context extraction pipeline for CRM notes."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone

from context_vault import cache, embedder, merger
from context_vault.models import AccountContext, ContactContext

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_DM_RE = re.compile(r"\b(?:CFO|CEO|CTO|VP\s+[A-Za-z]+)\b")
_BUDGET_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:[kKmMbB])?")


def _preprocess(raw_notes: str) -> str:
    stripped = _HTML_RE.sub(" ", raw_notes or "")
    return _WS_RE.sub(" ", stripped).strip()


def _extract_heuristics(text: str, account_id: str) -> AccountContext:
    decision_makers = sorted(set(m.group(0) for m in _DM_RE.finditer(text)))
    budget_match = _BUDGET_RE.search(text)

    contacts: list[ContactContext] = []
    for name in re.findall(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text)[:5]:
        contacts.append(ContactContext(name=name))

    contract_status = "prospect"
    if "customer" in text.lower():
        contract_status = "customer"
    elif "churn" in text.lower():
        contract_status = "churned"
    elif "closed-lost" in text.lower() or "lost" in text.lower():
        contract_status = "closed-lost"

    return AccountContext(
        account_id=account_id,
        account_name=account_id,
        extracted_contacts=contacts,
        decision_makers=decision_makers,
        contract_status=contract_status,
        budget=budget_match.group(0) if budget_match else None,
        timing="Q2 2026" if "q2" in text.lower() else None,
        next_action="Follow up" if text else None,
        last_enriched_at=datetime.now(timezone.utc),
    )


async def extract(raw_notes: str, account_id: str) -> AccountContext:
    processed = _preprocess(raw_notes)
    new_ctx = _extract_heuristics(processed, account_id)
    existing = await cache.get_or_fetch(account_id)
    merged = merger.merge(existing, new_ctx)
    asyncio.create_task(embedder.embed_and_store(merged, account_id))
    return merged
