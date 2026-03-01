"""Context extraction pipeline for CRM notes."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

from context_vault import cache, embedder, merger
from context_vault.models import AccountContext, ContactContext

_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_DM_RE = re.compile(r"\b(?:CFO|CEO|COO|CTO|CIO|CMO|VP\s+[A-Za-z]+|Head\s+of\s+[A-Za-z]+|Director\s+of\s+[A-Za-z]+)\b")
_BUDGET_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:[kKmMbB])?")
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_EMPLOYEES_RE = re.compile(r"\b(\d{2,6})\s+(?:employees|employee|headcount|staff)\b", re.IGNORECASE)
_TIMING_QUARTER_RE = re.compile(r"\bQ([1-4])\s*(20\d{2})\b", re.IGNORECASE)
_TIMING_MONTHS_RE = re.compile(r"\bin\s+(\d{1,2})\s+months?\b", re.IGNORECASE)

_INDUSTRY_HINTS = {
    "saas": "SaaS",
    "software": "Software",
    "healthcare": "Healthcare",
    "fintech": "Fintech",
    "manufacturing": "Manufacturing",
    "retail": "Retail",
    "education": "Education",
}

_NEXT_ACTION_HINTS = [
    ("follow up", "Follow up"),
    ("schedule demo", "Schedule demo"),
    ("book demo", "Schedule demo"),
    ("send proposal", "Send proposal"),
    ("pilot", "Start pilot"),
]

logger = logging.getLogger(__name__)


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in {"1", "true", "yes", "on"}


def _enrichment_min_confidence() -> float:
    raw = os.environ.get("EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN", "0.75").strip()
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "extractor_enrich_confidence_invalid",
            extra={"raw": raw, "fallback": 0.75},
        )
        return 0.75
    if not 0.0 <= value <= 1.0:
        logger.warning(
            "extractor_enrich_confidence_out_of_range",
            extra={"raw": raw, "fallback": 0.75},
        )
        return 0.75
    return value


def _preprocess(raw_notes: str) -> str:
    stripped = _HTML_RE.sub(" ", raw_notes or "")
    return _WS_RE.sub(" ", stripped).strip()


def _infer_industry(text: str) -> str | None:
    lower = text.lower()
    for keyword, value in _INDUSTRY_HINTS.items():
        if keyword in lower:
            return value
    return None


def _infer_timing(text: str) -> str | None:
    q_match = _TIMING_QUARTER_RE.search(text)
    if q_match:
        return f"Q{q_match.group(1)} {q_match.group(2)}"

    month_match = _TIMING_MONTHS_RE.search(text)
    if month_match:
        return f"in {month_match.group(1)} months"
    return None


def _infer_next_action(text: str) -> str | None:
    lower = text.lower()
    for needle, action in _NEXT_ACTION_HINTS:
        if needle in lower:
            return action
    return "Follow up" if text else None


def _infer_contract_status(text: str) -> str:
    lower = text.lower()
    if "closed-lost" in lower or "lost" in lower:
        return "closed-lost"
    if "churn" in lower:
        return "churned"
    if "customer" in lower:
        return "customer"
    return "prospect"


def _extract_contacts(text: str) -> tuple[list[ContactContext], str | None]:
    contacts: dict[str, ContactContext] = {}
    inferred_domain: str | None = None

    for local_part, domain in _EMAIL_RE.findall(text):
        name_guess = local_part.replace(".", " ").replace("_", " ").title()
        key = f"{local_part}@{domain}".lower()
        contacts[key] = ContactContext(name=name_guess, email=f"{local_part}@{domain}")
        inferred_domain = inferred_domain or domain.lower()

    for name in re.findall(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", text)[:8]:
        key = name.lower()
        contacts.setdefault(key, ContactContext(name=name))

    return list(contacts.values())[:8], inferred_domain


def _extract_heuristics(text: str, account_id: str) -> AccountContext:
    decision_makers = sorted(set(m.group(0) for m in _DM_RE.finditer(text)))
    budget_match = _BUDGET_RE.search(text)
    employee_match = _EMPLOYEES_RE.search(text)

    contacts, inferred_domain = _extract_contacts(text)
    timing = _infer_timing(text)

    return AccountContext(
        account_id=account_id,
        account_name=account_id,
        domain=inferred_domain,
        industry=_infer_industry(text),
        employee_count=int(employee_match.group(1)) if employee_match else None,
        extracted_contacts=contacts,
        decision_makers=decision_makers,
        contract_status=_infer_contract_status(text),
        budget=budget_match.group(0) if budget_match else None,
        timing=timing,
        next_action=_infer_next_action(text),
        last_enriched_at=datetime.now(timezone.utc),
    )


def _apply_confidence_overlay(base: AccountContext, enriched: AccountContext, confidence: dict[str, float]) -> AccountContext:
    min_conf = _enrichment_min_confidence()
    out = base.model_copy(deep=True)
    applied_fields: list[str] = []

    scalar_fields = ["industry", "timing", "next_action", "contract_status", "budget", "domain", "employee_count"]
    for field in scalar_fields:
        if confidence.get(field, 0.0) < min_conf:
            continue
        new_value = getattr(enriched, field, None)
        if new_value is not None and new_value != "":
            setattr(out, field, new_value)
            applied_fields.append(field)

    if confidence.get("decision_makers", 0.0) >= min_conf and enriched.decision_makers:
        out.decision_makers = sorted(set(out.decision_makers + enriched.decision_makers))
        applied_fields.append("decision_makers")
    if confidence.get("extracted_contacts", 0.0) >= min_conf and enriched.extracted_contacts:
        out.extracted_contacts = out.extracted_contacts + enriched.extracted_contacts
        applied_fields.append("extracted_contacts")

    logger.info(
        "extractor_enrichment_overlay",
        extra={
            "min_confidence": min_conf,
            "applied_fields": applied_fields,
            "available_confidence_fields": sorted(confidence.keys()),
        },
    )

    return out


async def _model_assisted_enrichment(text: str, account_id: str) -> tuple[AccountContext, dict[str, float]]:
    """Optional deterministic enrichment layer behind a feature flag.

    This simulates model-assisted extraction in local-safe mode by applying additional
    text rules and emitting confidence scores per field.
    """
    confidence: dict[str, float] = {}
    enriched = AccountContext(account_id=account_id, account_name=account_id, last_enriched_at=datetime.now(timezone.utc))
    lower = text.lower()

    if "renewal" in lower or "expansion" in lower:
        enriched.next_action = "Send proposal"
        confidence["next_action"] = 0.82
    if "pilot" in lower and "q" in lower:
        enriched.contract_status = "prospect"
        confidence["contract_status"] = 0.78
    if "security review" in lower:
        enriched.timing = enriched.timing or "in 2 months"
        confidence["timing"] = 0.80

    title_hits = sorted(set(m.group(0) for m in _DM_RE.finditer(text)))
    if title_hits:
        enriched.decision_makers = title_hits
        confidence["decision_makers"] = 0.84

    contacts, inferred_domain = _extract_contacts(text)
    if contacts:
        enriched.extracted_contacts = contacts
        confidence["extracted_contacts"] = 0.76
    if inferred_domain:
        enriched.domain = inferred_domain
        confidence["domain"] = 0.90

    return enriched, confidence


async def extract(raw_notes: str, account_id: str) -> AccountContext:
    processed = _preprocess(raw_notes)
    new_ctx = _extract_heuristics(processed, account_id)
    if _env_enabled("EMAILDJ_EXTRACTOR_ENABLE_ENRICHMENT"):
        enriched_ctx, confidence = await _model_assisted_enrichment(processed, account_id)
        new_ctx = _apply_confidence_overlay(new_ctx, enriched_ctx, confidence)
        logger.info("extractor_enrichment_applied", extra={"account_id": account_id})
    else:
        logger.info("extractor_enrichment_skipped", extra={"account_id": account_id, "reason": "flag_disabled"})
    existing = await cache.get_or_fetch(account_id)
    merged = merger.merge(existing, new_ctx)
    asyncio.create_task(embedder.embed_and_store(merged, account_id))
    return merged
