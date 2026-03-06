from __future__ import annotations

import re
from collections import Counter
from typing import Any

from .research_state import has_meaningful_research


FACT_KIND_VALUES = {"prospect_context", "seller_context", "seller_proof", "cta"}
HOOK_CONFIDENCE_VALUES = {"low", "medium", "high"}
HOOK_EVIDENCE_VALUES = {"weak", "moderate", "strong"}
OVERREACH_RISK_VALUES = {"low", "medium", "high"}
REQUIRED_FORBIDDEN_CLAIM_PATTERNS = (
    "saw your recent post",
    "noticed you recently",
    "congrats on [anything not in research_text]",
)
DEFAULT_PROHIBITED_OVERREACH = (
    "unsupported_recency",
    "unsupported_initiative",
    "prospect_as_proof",
    "role_as_certainty",
    "placeholder_as_evidence",
)

PROSPECT_SOURCE_FIELDS = {"name", "title", "company", "industry", "prospect_notes", "research_text"}
SELLER_CONTEXT_SOURCE_FIELDS = {"product_summary", "icp_description", "differentiators", "company_notes"}
SELLER_PROOF_SOURCE_FIELDS = {"proof_points"}
CTA_SOURCE_FIELDS = {"cta_type", "cta_final_line"}

RECENCY_MARKERS = (
    "recent",
    "recently",
    "this quarter",
    "this month",
    "last quarter",
    "last month",
    "january",
    "february",
    "march",
    "april",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "2024",
    "2025",
    "2026",
)

INITIATIVE_MARKERS = (
    "initiative",
    "program",
    "rollout",
    "rolled out",
    "launch",
    "launched",
    "expansion",
    "expanded",
    "announced",
    "hiring",
    "pilot",
    "sla",
    "target",
    "review cadence",
)

STRONG_CLAIM_MARKERS = (
    "will",
    "would",
    "clearly",
    "definitely",
    "specific need",
    "priority now",
    "must be",
    "is focused on",
    "is prioritizing",
)


def canonical_fact_kind(source_field: str) -> str:
    source = str(source_field or "").strip().lower()
    if source in FACT_KIND_VALUES:
        return source
    if source in PROSPECT_SOURCE_FIELDS:
        return "prospect_context"
    if source in SELLER_PROOF_SOURCE_FIELDS:
        return "seller_proof"
    if source in CTA_SOURCE_FIELDS:
        return "cta"
    return "seller_context"


def fact_kind_from_fact(fact: dict[str, Any]) -> str:
    source_field = str(fact.get("source_field") or "").strip().lower()
    if source_field:
        return canonical_fact_kind(source_field)
    return canonical_fact_kind(str(fact.get("fact_kind") or ""))


def fact_kind_counts(facts: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        counts[fact_kind_from_fact(fact)] += 1
    return {kind: int(counts.get(kind, 0)) for kind in FACT_KIND_VALUES}


def fact_map_by_id(facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(fact.get("fact_id") or "").strip(): fact
        for fact in facts
        if isinstance(fact, dict) and str(fact.get("fact_id") or "").strip()
    }


def hook_supported_fact_ids(hook: dict[str, Any]) -> list[str]:
    return [str(item or "").strip() for item in (hook.get("supported_by_fact_ids") or []) if str(item or "").strip()]


def hook_seller_fact_ids(hook: dict[str, Any]) -> list[str]:
    return [str(item or "").strip() for item in (hook.get("seller_fact_ids") or []) if str(item or "").strip()]


def hook_confidence_level(hook: dict[str, Any]) -> str:
    value = str(hook.get("confidence_level") or "").strip().lower()
    return value if value in HOOK_CONFIDENCE_VALUES else "low"


def hook_evidence_strength(hook: dict[str, Any]) -> str:
    value = str(hook.get("evidence_strength") or "").strip().lower()
    return value if value in HOOK_EVIDENCE_VALUES else "weak"


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in markers)


def hook_mentions_recency(hook: dict[str, Any]) -> bool:
    merged = " ".join(
        str(hook.get(key) or "")
        for key in ("grounded_observation", "inferred_relevance", "seller_support", "hook_text")
    )
    return _contains_marker(merged, RECENCY_MARKERS)


def hook_mentions_initiative(hook: dict[str, Any]) -> bool:
    merged = " ".join(
        str(hook.get(key) or "")
        for key in ("grounded_observation", "inferred_relevance", "seller_support", "hook_text")
    )
    return _contains_marker(merged, INITIATIVE_MARKERS)


def hook_has_strong_claim_language(hook: dict[str, Any]) -> bool:
    merged = " ".join(
        str(hook.get(key) or "")
        for key in ("grounded_observation", "inferred_relevance", "seller_support", "hook_text")
    )
    return _contains_marker(merged, STRONG_CLAIM_MARKERS)


def supported_fact_kinds(hook: dict[str, Any], fact_map: dict[str, dict[str, Any]]) -> set[str]:
    kinds: set[str] = set()
    for fact_id in hook_supported_fact_ids(hook):
        fact = fact_map.get(fact_id) or {}
        kinds.add(fact_kind_from_fact(fact))
    return kinds


def seller_fact_kinds(hook: dict[str, Any], fact_map: dict[str, dict[str, Any]]) -> set[str]:
    kinds: set[str] = set()
    for fact_id in hook_seller_fact_ids(hook):
        fact = fact_map.get(fact_id) or {}
        kinds.add(fact_kind_from_fact(fact))
    return kinds


def hook_has_seller_proof(hook: dict[str, Any], fact_map: dict[str, dict[str, Any]]) -> bool:
    return "seller_proof" in seller_fact_kinds(hook, fact_map)


def hook_requires_grounded_research(hook: dict[str, Any]) -> bool:
    return str(hook.get("hook_type") or "").strip().lower() in {"initiative", "trigger_event"} or hook_mentions_recency(hook) or hook_mentions_initiative(hook)


def hook_is_prospect_as_proof(hook: dict[str, Any], fact_map: dict[str, dict[str, Any]]) -> bool:
    seller_support = str(hook.get("seller_support") or "").strip()
    if not seller_support:
        return False
    seller_kinds = seller_fact_kinds(hook, fact_map)
    if seller_kinds and seller_kinds.issubset({"seller_context", "seller_proof"}):
        return False
    supported_kinds = supported_fact_kinds(hook, fact_map)
    if "prospect_context" in supported_kinds and not seller_kinds:
        return True
    return "prospect_context" in seller_kinds or "cta" in seller_kinds


def compute_overreach_risk(brief: dict[str, Any]) -> str:
    hooks = [item for item in (brief.get("hooks") or []) if isinstance(item, dict)]
    facts = [item for item in (brief.get("facts_from_input") or []) if isinstance(item, dict)]
    fact_map = fact_map_by_id(facts)

    if any(hook_is_prospect_as_proof(hook, fact_map) for hook in hooks):
        return "high"
    if any(
        hook_confidence_level(hook) == "high" and not hook_has_seller_proof(hook, fact_map)
        for hook in hooks
    ):
        return "high"
    if any(hook_requires_grounded_research(hook) and not any((fact_map.get(fid) or {}).get("source_field") == "research_text" for fid in hook_supported_fact_ids(hook)) for hook in hooks):
        return "medium"
    return "low"


def signal_strength_from_brief(brief: dict[str, Any], *, source_text: str = "") -> str:
    facts = [item for item in (brief.get("facts_from_input") or []) if isinstance(item, dict)]
    hooks = [item for item in (brief.get("hooks") or []) if isinstance(item, dict)]
    fact_map = fact_map_by_id(facts)
    counts = fact_kind_counts(facts)
    has_research = has_meaningful_research(source_text) if source_text else any(
        str(fact.get("source_field") or "").strip().lower() == "research_text"
        for fact in facts
    )
    prospect_research_count = sum(1 for fact in facts if str(fact.get("source_field") or "").strip().lower() == "research_text")
    strong_hook_count = sum(
        1
        for hook in hooks
        if hook_evidence_strength(hook) == "strong" and hook_has_seller_proof(hook, fact_map)
    )

    if has_research and prospect_research_count >= 1 and counts["seller_proof"] >= 1 and strong_hook_count >= 1:
        return "high"
    if has_research or counts["seller_proof"] >= 1:
        return "medium"
    return "low"


def signal_strength_matches(brief: dict[str, Any], *, source_text: str = "") -> bool:
    quality = brief.get("brief_quality") if isinstance(brief.get("brief_quality"), dict) else {}
    signal_strength = str(quality.get("signal_strength") or "").strip().lower()
    if not signal_strength:
        return True
    return signal_strength == signal_strength_from_brief(brief, source_text=source_text)


def normalize_forbidden_claim_patterns(patterns: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in list(patterns or []) + list(REQUIRED_FORBIDDEN_CLAIM_PATTERNS):
        text = normalize_text_key(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def normalize_prohibited_overreach(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in list(values or []) + list(DEFAULT_PROHIBITED_OVERREACH):
        text = normalize_text_key(raw)
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def derive_brief_quality(brief: dict[str, Any], *, source_text: str = "") -> dict[str, Any]:
    facts = [item for item in (brief.get("facts_from_input") or []) if isinstance(item, dict)]
    assumptions = [item for item in (brief.get("assumptions") or []) if isinstance(item, dict)]
    hooks = [item for item in (brief.get("hooks") or []) if isinstance(item, dict)]
    existing = brief.get("brief_quality") if isinstance(brief.get("brief_quality"), dict) else {}
    quality_notes = [
        str(item).strip()
        for item in (existing.get("quality_notes") or [])
        if str(item).strip()
    ]
    kind_counts = fact_kind_counts(facts)
    assumption_confidences = [
        max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
        for item in assumptions
        if isinstance(item, dict)
    ]
    hook_confidence_ceiling = {
        "low": 0.45,
        "medium": 0.65,
        "high": 0.85,
    }
    hook_confidences = [
        hook_confidence_ceiling.get(hook_confidence_level(item), 0.0)
        for item in hooks
    ]
    confidence_ceiling = 0.0
    if assumption_confidences or hook_confidences:
        confidence_ceiling = round(max([*assumption_confidences, *hook_confidences]), 2)

    return {
        "fact_count": len(facts),
        "assumption_count": len(assumptions),
        "hook_count": len(hooks),
        "has_research": has_meaningful_research(source_text) if source_text else any(
            str(fact.get("source_field") or "").strip().lower() == "research_text"
            for fact in facts
        ),
        "grounded_fact_count": kind_counts["prospect_context"] + kind_counts["seller_context"] + kind_counts["seller_proof"],
        "prospect_context_fact_count": kind_counts["prospect_context"],
        "seller_context_fact_count": kind_counts["seller_context"],
        "seller_proof_fact_count": kind_counts["seller_proof"],
        "cta_fact_count": kind_counts["cta"],
        "confidence_ceiling": confidence_ceiling,
        "signal_strength": signal_strength_from_brief(brief, source_text=source_text),
        "overreach_risk": compute_overreach_risk(brief),
        "quality_notes": quality_notes,
    }


def normalize_text_key(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())
