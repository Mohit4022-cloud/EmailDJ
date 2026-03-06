from __future__ import annotations

from copy import deepcopy
from typing import Any

from .brief_honesty import (
    CONFIDENCE_LEVEL_ORDER,
    EVIDENCE_STRENGTH_ORDER,
    canonical_fact_kind,
    contaminated_research_fact_ids,
    derive_brief_quality,
    fact_map_by_id,
    hook_confidence_level,
    hook_evidence_strength,
    hook_support_posture,
    normalize_text_key,
    normalize_forbidden_claim_patterns,
    normalize_prohibited_overreach,
)
from .research_state import is_placeholder_fact_text, is_semantic_no_research, normalize_placeholder_text
from .schemas import ALLOWED_STAGE_A_SOURCE_FIELDS


_STRUCTURAL_PLACEHOLDERS = {"", "/", "-"}
_HOOK_LIST_FIELDS = ("supported_by_fact_ids", "seller_fact_ids", "risk_flags")
_PERSONA_LIST_FIELDS = ("likely_kpis", "likely_initiatives", "day_to_day", "tools_stack")
_CONFIDENCE_LEVEL_BY_ORDER = {value: key for key, value in CONFIDENCE_LEVEL_ORDER.items()}
_EVIDENCE_STRENGTH_BY_ORDER = {value: key for key, value in EVIDENCE_STRENGTH_ORDER.items()}


def _is_placeholder_text(value: Any) -> bool:
    normalized = normalize_placeholder_text(value)
    return normalized in _STRUCTURAL_PLACEHOLDERS or is_placeholder_fact_text(value) or is_semantic_no_research(value)


def _flatten_input_text(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            out.extend(_flatten_input_text(item))
        return out
    if isinstance(value, list):
        for item in value:
            out.extend(_flatten_input_text(item))
        return out
    text = str(value or "").strip()
    if text and not _is_placeholder_text(text):
        out.append(text)
    return out


def _field_has_usable_signal(value: Any) -> bool:
    return bool(_flatten_input_text(value))


def _source_field_value_map(source_payload: dict[str, Any]) -> dict[str, Any]:
    user_company = dict(source_payload.get("user_company") or {})
    prospect = dict(source_payload.get("prospect") or {})
    cta = dict(source_payload.get("cta") or {})
    return {
        "name": prospect.get("name"),
        "title": prospect.get("title"),
        "company": prospect.get("company"),
        "industry": prospect.get("industry"),
        "prospect_notes": prospect.get("notes"),
        "research_text": prospect.get("research_text"),
        "product_summary": user_company.get("product_summary"),
        "icp_description": user_company.get("icp_description"),
        "differentiators": user_company.get("differentiators"),
        "proof_points": user_company.get("proof_points"),
        "do_not_say": user_company.get("do_not_say"),
        "company_notes": user_company.get("company_notes"),
        "cta_type": cta.get("cta_type"),
        "cta_final_line": cta.get("cta_final_line"),
    }


def _normalized_string_list(value: Any) -> list[str]:
    raw_items = value if isinstance(value, list) else [value]
    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_items:
        text = str(raw or "").strip()
        if not text or _is_placeholder_text(text):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _normalize_persona_cues(raw: Any) -> dict[str, Any]:
    cues = dict(raw or {}) if isinstance(raw, dict) else {}
    return {
        "likely_kpis": _normalized_string_list(cues.get("likely_kpis") or []),
        "likely_initiatives": _normalized_string_list(cues.get("likely_initiatives") or []),
        "day_to_day": _normalized_string_list(cues.get("day_to_day") or []),
        "tools_stack": _normalized_string_list(cues.get("tools_stack") or []),
        "notes": "" if _is_placeholder_text(cues.get("notes")) else str(cues.get("notes") or "").strip(),
    }


def _cap_ordered_value(
    current: str,
    max_allowed: str,
    *,
    order: dict[str, int],
    reverse_order: dict[int, str],
) -> str:
    capped_order = min(order.get(current, 0), order.get(max_allowed, 0))
    return reverse_order.get(capped_order, max_allowed)


def _derived_allowed_personalization_fact_sources(
    *,
    source_payload: dict[str, Any] | None,
    facts: list[dict[str, Any]],
) -> list[str]:
    if source_payload:
        source_field_map = _source_field_value_map(source_payload)
        return [
            field
            for field in ALLOWED_STAGE_A_SOURCE_FIELDS
            if _field_has_usable_signal(source_field_map.get(field))
        ]

    seen: set[str] = set()
    allowed: list[str] = []
    for fact in facts:
        field = str(fact.get("source_field") or "").strip().lower()
        text = str(fact.get("text") or "").strip()
        if not field or field not in ALLOWED_STAGE_A_SOURCE_FIELDS or _is_placeholder_text(text) or field in seen:
            continue
        seen.add(field)
        allowed.append(field)
    return allowed


def _apply_stage_a_defaults(
    brief: dict[str, Any],
    *,
    source_text: str,
    source_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    facts = [item for item in (brief.get("facts_from_input") or []) if isinstance(item, dict)]
    for fact in facts:
        source_field = str(fact.get("source_field") or "").strip().lower()
        if source_field:
            fact["source_field"] = source_field
            fact["fact_kind"] = canonical_fact_kind(source_field)

    brief["persona_cues"] = _normalize_persona_cues(brief.get("persona_cues"))
    brief["do_not_say"] = _normalized_string_list(brief.get("do_not_say") or [])
    brief["forbidden_claim_patterns"] = normalize_forbidden_claim_patterns(
        _normalized_string_list(brief.get("forbidden_claim_patterns") or [])
    )
    brief["prohibited_overreach"] = normalize_prohibited_overreach(
        _normalized_string_list(brief.get("prohibited_overreach") or [])
    )
    brief["grounding_policy"] = {
        "no_new_facts": True,
        "no_ungrounded_personalization": True,
        "allowed_personalization_fact_sources": _derived_allowed_personalization_fact_sources(
            source_payload=source_payload,
            facts=facts,
        ),
    }
    brief["brief_quality"] = derive_brief_quality(brief, source_text=source_text)
    return brief


def _summary_snapshot(brief: dict[str, Any]) -> dict[str, Any]:
    quality = brief.get("brief_quality") if isinstance(brief.get("brief_quality"), dict) else {}
    return {
        "fact_count": int(quality.get("fact_count") or 0),
        "hook_count": int(quality.get("hook_count") or 0),
        "seller_proof_fact_count": int(quality.get("seller_proof_fact_count") or 0),
        "signal_strength": str(quality.get("signal_strength") or "").strip().lower(),
        "overreach_risk": str(quality.get("overreach_risk") or "").strip().lower(),
    }


def _append_issue(issues: list[dict[str, Any]], code: str, **kwargs: Any) -> None:
    issues.append({"code": code, **kwargs})


def inspect_stage_a_raw_hygiene(
    raw_brief: dict[str, Any],
    *,
    source_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    facts = [item for item in (raw_brief.get("facts_from_input") or []) if isinstance(item, dict)]
    hooks = [item for item in (raw_brief.get("hooks") or []) if isinstance(item, dict)]
    persona_cues = dict(raw_brief.get("persona_cues") or {})
    source_field_map = _source_field_value_map(source_payload or {}) if source_payload else {}
    seen_fact_keys: set[tuple[str, str]] = set()

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        source_field = str(fact.get("source_field") or "").strip()
        text = str(fact.get("text") or "").strip()
        if not fact_id or not source_field or not text:
            _append_issue(
                issues,
                "fact_row_incomplete",
                fact_id=fact_id,
                source_field=source_field,
            )
        if source_field and source_field not in ALLOWED_STAGE_A_SOURCE_FIELDS:
            _append_issue(
                issues,
                "fact_source_field_invalid",
                fact_id=fact_id,
                source_field=source_field,
            )
        if _is_placeholder_text(text):
            _append_issue(
                issues,
                "fact_placeholder_text",
                fact_id=fact_id,
                source_field=source_field,
                offending_text=text[:160],
            )
        normalized_fact_key = (source_field.lower(), normalize_text_key(text))
        if text and normalized_fact_key in seen_fact_keys:
            _append_issue(
                issues,
                "fact_duplicate_text_same_source",
                fact_id=fact_id,
                source_field=source_field,
                offending_text=text[:160],
            )
        if text:
            seen_fact_keys.add(normalized_fact_key)
        if source_field and source_payload and not _field_has_usable_signal(source_field_map.get(source_field.lower())):
            _append_issue(
                issues,
                "fact_source_without_input_signal",
                fact_id=fact_id,
                source_field=source_field,
                offending_text=text[:160],
            )

    for hook in hooks:
        hook_id = str(hook.get("hook_id") or "").strip()
        for field in ("grounded_observation", "inferred_relevance", "seller_support"):
            value = str(hook.get(field) or "").strip()
            if value and _is_placeholder_text(value):
                _append_issue(
                    issues,
                    "hook_placeholder_subfield",
                    hook_id=hook_id,
                    field=field,
                    offending_text=value[:160],
                )
        for field in _HOOK_LIST_FIELDS:
            raw_items = hook.get(field) if isinstance(hook.get(field), list) else []
            for item in raw_items:
                if not str(item or "").strip():
                    _append_issue(
                        issues,
                        "hook_empty_list_entry",
                        hook_id=hook_id,
                        field=field,
                    )
        if str(hook.get("seller_support") or "").strip() and not [
            str(item or "").strip() for item in (hook.get("seller_fact_ids") or []) if str(item or "").strip()
        ]:
            _append_issue(
                issues,
                "hook_unbacked_seller_support",
                hook_id=hook_id,
            )
        cleaned_supported = [str(item or "").strip() for item in (hook.get("supported_by_fact_ids") or []) if str(item or "").strip()]
        if not hook_id or not str(hook.get("hook_text") or "").strip() or not cleaned_supported:
            _append_issue(
                issues,
                "hook_structurally_empty",
                hook_id=hook_id,
            )

    notes = persona_cues.get("notes")
    if str(notes or "").strip() and _is_placeholder_text(notes):
        _append_issue(issues, "persona_placeholder_note")
    for field in _PERSONA_LIST_FIELDS:
        raw_items = persona_cues.get(field) if isinstance(persona_cues.get(field), list) else []
        for item in raw_items:
            if _is_placeholder_text(item):
                _append_issue(
                    issues,
                    "persona_placeholder_item",
                    field=field,
                    offending_text=str(item or "")[:160],
                )

    issue_codes = sorted({str(item.get("code") or "").strip() for item in issues if str(item.get("code") or "").strip()})
    return {
        "raw_hygiene_issues": issues,
        "raw_artifact_quality": {
            "issue_count": len(issues),
            "issue_codes": issue_codes,
            "status": "sloppy" if issues else "clean",
        },
    }


def sanitize_stage_a_brief(
    raw_brief: dict[str, Any],
    *,
    source_text: str = "",
    source_payload: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sanitized = deepcopy(raw_brief if isinstance(raw_brief, dict) else {})
    raw_hygiene_flags = inspect_stage_a_raw_hygiene(sanitized, source_payload=source_payload)
    action_counts: dict[str, int] = {}
    actions: list[dict[str, Any]] = []

    def record(action: str, **kwargs: Any) -> None:
        action_counts[action] = action_counts.get(action, 0) + 1
        actions.append({"action": action, **kwargs})

    raw_summary_brief = _apply_stage_a_defaults(
        deepcopy(raw_brief if isinstance(raw_brief, dict) else {}),
        source_text=source_text,
        source_payload=source_payload,
    )
    before_summary = _summary_snapshot(raw_summary_brief)
    source_field_map = _source_field_value_map(source_payload or {}) if source_payload else {}
    seen_fact_keys: set[tuple[str, str]] = set()

    sanitized_facts: list[dict[str, Any]] = []
    for fact in sanitized.get("facts_from_input") or []:
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("fact_id") or "").strip()
        source_field = str(fact.get("source_field") or "").strip()
        text = str(fact.get("text") or "").strip()
        if not fact_id:
            record("drop_fact_blank_fact_id", source_field=source_field, reason="blank_fact_id")
            continue
        if not source_field:
            record("drop_fact_blank_source_field", fact_id=fact_id, reason="blank_source_field")
            continue
        if not text:
            record("drop_fact_blank_text", fact_id=fact_id, source_field=source_field, reason="blank_text")
            continue
        if _is_placeholder_text(text):
            record(
                "drop_fact_placeholder_text",
                fact_id=fact_id,
                source_field=source_field,
                reason="placeholder_text",
            )
            continue
        if source_payload and not _field_has_usable_signal(source_field_map.get(source_field.lower())):
            record(
                "drop_fact_source_without_input_signal",
                fact_id=fact_id,
                source_field=source_field,
                reason="no_input_signal",
            )
            continue
        normalized_fact_key = (source_field.lower(), normalize_text_key(text))
        if normalized_fact_key in seen_fact_keys:
            record(
                "drop_fact_duplicate_text_same_source",
                fact_id=fact_id,
                source_field=source_field,
                reason="duplicate_text_same_source",
            )
            continue
        seen_fact_keys.add(normalized_fact_key)
        fact["source_field"] = source_field.lower()
        fact["fact_kind"] = canonical_fact_kind(fact["source_field"])
        sanitized_facts.append(fact)
    sanitized["facts_from_input"] = sanitized_facts
    valid_fact_ids = {
        str(fact.get("fact_id") or "").strip()
        for fact in sanitized_facts
        if str(fact.get("fact_id") or "").strip()
    }

    sanitized_assumptions: list[dict[str, Any]] = []
    for assumption in sanitized.get("assumptions") or []:
        if not isinstance(assumption, dict):
            continue
        based_on = [str(item or "").strip() for item in (assumption.get("based_on_fact_ids") or []) if str(item or "").strip()]
        if len(based_on) != len(assumption.get("based_on_fact_ids") or []):
            record(
                "drop_assumption_empty_based_on_fact_id",
                assumption_id=str(assumption.get("assumption_id") or "").strip(),
                reason="empty_based_on_fact_id",
            )
        assumption["based_on_fact_ids"] = based_on
        sanitized_assumptions.append(assumption)
    sanitized["assumptions"] = sanitized_assumptions

    sanitized_hooks: list[dict[str, Any]] = []
    for hook in sanitized.get("hooks") or []:
        if not isinstance(hook, dict):
            continue
        hook_id = str(hook.get("hook_id") or "").strip()
        for field in ("grounded_observation", "inferred_relevance", "seller_support"):
            value = str(hook.get(field) or "").strip()
            if value and _is_placeholder_text(value):
                hook[field] = ""
                record(
                    "normalize_hook_placeholder_subfield",
                    hook_id=hook_id,
                    field=field,
                    reason="placeholder_text",
                )
            else:
                hook[field] = value

        if hook.get("seller_support") and not [
            str(item or "").strip() for item in (hook.get("seller_fact_ids") or []) if str(item or "").strip()
        ]:
            hook["seller_support"] = ""
            record(
                "normalize_hook_unbacked_seller_support",
                hook_id=hook_id,
                reason="missing_seller_fact_ids",
            )

        for field in _HOOK_LIST_FIELDS:
            cleaned = [str(item or "").strip() for item in (hook.get(field) or []) if str(item or "").strip()]
            removed = len(hook.get(field) or []) - len(cleaned)
            if removed:
                record(
                    f"drop_hook_empty_{field}",
                    hook_id=hook_id,
                    field=field,
                    removed=removed,
                    reason="empty_list_entry",
                )
            hook[field] = cleaned

        for field in ("supported_by_fact_ids", "seller_fact_ids"):
            filtered = [item for item in hook.get(field) or [] if item in valid_fact_ids]
            removed = len(hook.get(field) or []) - len(filtered)
            if removed:
                record(
                    "drop_hook_missing_fact_reference",
                    hook_id=hook_id,
                    field=field,
                    removed=removed,
                    reason="removed_fact_reference",
                )
            hook[field] = filtered

        if not hook_id or not str(hook.get("hook_type") or "").strip() or not str(hook.get("hook_text") or "").strip():
            record("drop_hook_structurally_empty", hook_id=hook_id, reason="missing_core_fields")
            continue
        if not str(hook.get("grounded_observation") or "").strip() or not str(hook.get("inferred_relevance") or "").strip():
            record("drop_hook_structurally_empty", hook_id=hook_id, reason="missing_supporting_fields")
            continue
        if not hook.get("supported_by_fact_ids"):
            record("drop_hook_structurally_empty", hook_id=hook_id, reason="missing_supported_by_fact_ids")
            continue
        sanitized_hooks.append(hook)
    sanitized["hooks"] = sanitized_hooks

    fact_map = fact_map_by_id(sanitized_facts)
    contaminated_fact_ids = contaminated_research_fact_ids(sanitized_facts)
    for hook in sanitized["hooks"]:
        hook_id = str(hook.get("hook_id") or "").strip()
        posture = hook_support_posture(hook, fact_map, contaminated_fact_ids=contaminated_fact_ids)

        risk_flags = [str(item or "").strip() for item in (hook.get("risk_flags") or []) if str(item or "").strip()]
        for required_flag in posture["required_risk_flags"]:
            if required_flag in risk_flags:
                continue
            risk_flags.append(required_flag)
            record(
                "add_hook_required_risk_flag",
                hook_id=hook_id,
                flag=required_flag,
                reason="required_by_hook_posture",
            )
        hook["risk_flags"] = risk_flags

        current_confidence = hook_confidence_level(hook)
        capped_confidence = _cap_ordered_value(
            current_confidence,
            posture["max_confidence_level"],
            order=CONFIDENCE_LEVEL_ORDER,
            reverse_order=_CONFIDENCE_LEVEL_BY_ORDER,
        )
        if capped_confidence != current_confidence:
            hook["confidence_level"] = capped_confidence
            record(
                "cap_hook_confidence_level",
                hook_id=hook_id,
                from_value=current_confidence,
                to_value=capped_confidence,
                reason="seller_proof_cap",
            )

        current_evidence = hook_evidence_strength(hook)
        capped_evidence = _cap_ordered_value(
            current_evidence,
            posture["max_evidence_strength"],
            order=EVIDENCE_STRENGTH_ORDER,
            reverse_order=_EVIDENCE_STRENGTH_BY_ORDER,
        )
        if capped_evidence != current_evidence:
            hook["evidence_strength"] = capped_evidence
            record(
                "cap_hook_evidence_strength",
                hook_id=hook_id,
                from_value=current_evidence,
                to_value=capped_evidence,
                reason="seller_proof_cap",
            )

    persona_cues = dict(sanitized.get("persona_cues") or {})
    if str(persona_cues.get("notes") or "").strip() and _is_placeholder_text(persona_cues.get("notes")):
        persona_cues["notes"] = ""
        record("normalize_persona_placeholder_note", reason="placeholder_text")
    for field in _PERSONA_LIST_FIELDS:
        raw_items = persona_cues.get(field) if isinstance(persona_cues.get(field), list) else []
        cleaned = [str(item or "").strip() for item in raw_items if str(item or "").strip() and not _is_placeholder_text(item)]
        removed = len(raw_items) - len(cleaned)
        if removed:
            record(
                "drop_persona_placeholder_item",
                field=field,
                removed=removed,
                reason="placeholder_text",
            )
        persona_cues[field] = cleaned
    sanitized["persona_cues"] = persona_cues

    sanitized = _apply_stage_a_defaults(
        sanitized,
        source_text=source_text,
        source_payload=source_payload,
    )
    after_summary = _summary_snapshot(sanitized)

    semantic_change_reasons = [
        key
        for key in ("fact_count", "hook_count", "seller_proof_fact_count", "signal_strength", "overreach_risk")
        if before_summary.get(key) != after_summary.get(key)
    ]
    if any(
        action_counts.get(key, 0)
        for key in (
            "drop_hook_empty_supported_by_fact_ids",
            "drop_hook_empty_seller_fact_ids",
            "normalize_hook_placeholder_subfield",
            "add_hook_required_risk_flag",
            "cap_hook_confidence_level",
            "cap_hook_evidence_strength",
            "normalize_hook_unbacked_seller_support",
            "drop_hook_missing_fact_reference",
        )
    ):
        semantic_change_reasons.append("hook_support_posture")

    sanitation_report = {
        "sanitation_action_counts": action_counts,
        "actions": actions,
        "before": before_summary,
        "after": after_summary,
        "removed_fact_ids": [
            str(item.get("fact_id") or "").strip()
            for item in actions
            if str(item.get("action") or "").startswith("drop_fact_") and str(item.get("fact_id") or "").strip()
        ],
        "removed_hook_ids": [
            str(item.get("hook_id") or "").strip()
            for item in actions
            if str(item.get("action") or "") == "drop_hook_structurally_empty" and str(item.get("hook_id") or "").strip()
        ],
        "sanitation_changed_semantic_eligibility": bool(semantic_change_reasons),
        "semantic_change_reasons": semantic_change_reasons,
    }
    return sanitized, sanitation_report, raw_hygiene_flags
