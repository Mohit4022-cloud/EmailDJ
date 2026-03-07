from __future__ import annotations

from collections import Counter
import re
from difflib import SequenceMatcher
from typing import Any

from .budget_planner import (
    atom_structure,
    atom_word_counts,
    cta_alignment_status,
    plan_budget,
)
from .preset_contract import sentence_count as contract_sentence_count

from .brief_honesty import (
    CONFIDENCE_LEVEL_ORDER,
    EVIDENCE_STRENGTH_ORDER,
    HOOK_CONFIDENCE_VALUES,
    HOOK_EVIDENCE_VALUES,
    OVERREACH_RISK_VALUES,
    canonical_fact_kind,
    contaminated_research_fact_ids,
    derive_brief_quality,
    fact_map_by_id,
    hook_confidence_level,
    hook_evidence_strength,
    normalize_forbidden_claim_patterns,
    normalize_prohibited_overreach,
    hook_has_strong_claim_language,
    hook_is_prospect_as_proof,
    hook_mentions_initiative,
    hook_mentions_recency,
    hook_requires_grounded_research,
    hook_support_posture,
    hook_seller_fact_ids,
    hook_supported_fact_ids,
    normalize_text_key,
    seller_fact_kinds,
    signal_strength_matches,
)
from .research_state import is_placeholder_fact_text, is_semantic_no_research, normalize_placeholder_text
from .schemas import ALLOWED_STAGE_A_SOURCE_FIELDS


BANNED_PHRASES = [
    "touch base",
    "circle back",
    "synergy",
    "leverage",
    "game-changer",
    "revolutionary",
    "i hope this email finds you",
    "i wanted to reach out",
    "just checking in",
]

UNGROUNDED_PERSONALIZATION_MARKERS = [
    "saw your post",
    "noticed you",
    "congrats on",
    "just came across",
]

MECHANICAL_VALIDATION_CODES = {
    "subject_too_long",
    "cta_not_final_line",
    "duplicate_cta_line",
    "word_count_out_of_band",
    "too_many_sentences_for_preset",
}

SEMANTIC_VALIDATION_CODES = {
    "banned_phrase",
    "ungrounded_personalization_claim",
    "repetition_detected",
    "personalization_missing_used_hook",
    "personalization_generic_opener",
}

GROUNDING_STOPWORDS = {
    "about",
    "after",
    "also",
    "and",
    "are",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "could",
    "from",
    "have",
    "into",
    "more",
    "most",
    "that",
    "their",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "with",
    "would",
}


class ValidationIssue(ValueError):
    def __init__(
        self,
        codes: list[str],
        message: str = "validation_failed",
        *,
        details: list[dict[str, Any]] | None = None,
    ):
        super().__init__(message)
        self.codes = list(codes)
        self.details = list(details or [])


def _codes_or_raise(codes: list[str], details: list[dict[str, Any]] | None = None) -> None:
    if codes:
        raise ValidationIssue(codes, details=details)


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
    if text and not _is_placeholder_input_text(text):
        out.append(text)
    return out


def _grounding_tokens(text: str) -> set[str]:
    tokens = re.findall(r"[a-z0-9']+", str(text or "").lower())
    return {token for token in tokens if len(token) >= 4 and token not in GROUNDING_STOPWORDS}


def _numeric_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"\b\d+(?:\.\d+)?%?\b", str(text or "").lower())}


def _normalize_placeholder_text(text: Any) -> str:
    return normalize_placeholder_text(text)


def _is_placeholder_input_text(text: Any) -> bool:
    return is_placeholder_fact_text(text) or is_semantic_no_research(text)


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
        if not text:
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
        "notes": str(cues.get("notes") or "").strip(),
    }


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
        if not field or field not in ALLOWED_STAGE_A_SOURCE_FIELDS or _is_placeholder_input_text(text) or field in seen:
            continue
        seen.add(field)
        allowed.append(field)
    return allowed


def _normalize_stage_a_brief_defaults(
    brief: dict[str, Any],
    *,
    source_text: str,
    source_payload: dict[str, Any] | None,
    facts: list[dict[str, Any]],
) -> None:
    input_do_not_say: list[str] = []
    if source_payload:
        raw_do_not_say = _source_field_value_map(source_payload).get("do_not_say")
        if isinstance(raw_do_not_say, list):
            input_do_not_say = _normalized_string_list(raw_do_not_say)
    existing_do_not_say = brief.get("do_not_say")
    existing_do_not_say_items = (
        existing_do_not_say
        if isinstance(existing_do_not_say, list)
        else ([existing_do_not_say] if existing_do_not_say else [])
    )
    brief["persona_cues"] = _normalize_persona_cues(brief.get("persona_cues"))
    brief["do_not_say"] = _normalized_string_list([*input_do_not_say, *existing_do_not_say_items])
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


def _field_has_usable_signal(value: Any) -> bool:
    return bool(_flatten_input_text(value))


def _has_placeholder_leakage(values: list[Any]) -> bool:
    return any(_normalize_placeholder_text(item) and _is_placeholder_input_text(item) for item in values)


def _append_detail(details: list[dict[str, Any]], code: str, **kwargs: Any) -> None:
    details.append({"code": code, **kwargs})


def validate_messaging_brief(
    brief: dict[str, Any],
    *,
    source_text: str = "",
    source_payload: dict[str, Any] | None = None,
) -> None:
    codes: list[str] = []
    facts = [item for item in (brief.get("facts_from_input") or []) if isinstance(item, dict)]
    assumptions = [item for item in (brief.get("assumptions") or []) if isinstance(item, dict)]
    hooks = [item for item in (brief.get("hooks") or []) if isinstance(item, dict)]
    details: list[dict[str, Any]] = []

    if len(facts) < 1:
        codes.append("brief_missing_facts")
    if len(hooks) < 1:
        codes.append("brief_missing_hooks")

    for fact in facts:
        source_field = str(fact.get("source_field") or "").strip().lower()
        if source_field:
            fact["source_field"] = source_field
            fact["fact_kind"] = canonical_fact_kind(source_field)

    _normalize_stage_a_brief_defaults(
        brief,
        source_text=source_text,
        source_payload=source_payload,
        facts=facts,
    )

    brief_quality = dict(brief.get("brief_quality") or {})
    prohibited_overreach = [str(item or "").strip().lower() for item in (brief.get("prohibited_overreach") or [])]
    fact_map = fact_map_by_id(facts)
    prospect_company = ""
    source_text_occurrences: Counter[str] = Counter()
    if source_payload:
        source_field_map = _source_field_value_map(source_payload)
        prospect_company = str(source_field_map.get("company") or "").strip()
        source_text_occurrences = Counter(
            normalize_text_key(fragment)
            for fragment in _flatten_input_text(list(source_field_map.values()))
            if normalize_text_key(fragment)
        )
    contaminated_fact_ids = contaminated_research_fact_ids(facts, prospect_company=prospect_company or None)
    normalized_fact_keys: set[tuple[str, str]] = set()

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        fact_text = str(fact.get("text") or "").strip()
        source_field = str(fact.get("source_field") or "").strip().lower()
        fact_kind = canonical_fact_kind(source_field)

        if _is_placeholder_input_text(fact_text):
            codes.append("fact_placeholder_text")
            _append_detail(
                details,
                "fact_placeholder_text",
                fact_id=fact_id,
                source_field=source_field,
                offending_text=fact_text[:160],
            )
            break

        if source_field and source_field not in ALLOWED_STAGE_A_SOURCE_FIELDS:
            codes.append("fact_source_field_not_allowed")
            _append_detail(
                details,
                "fact_source_field_not_allowed",
                fact_id=fact_id,
                source_field=source_field,
                offending_text=fact_text[:160],
            )
            break

        fact_key = (fact_kind, normalize_text_key(fact_text))
        if fact_key in normalized_fact_keys and fact_kind != "cta":
            if source_text_occurrences.get(normalize_text_key(fact_text), 0) <= 1:
                codes.append("fact_duplicate_text")
                _append_detail(
                    details,
                    "fact_duplicate_text",
                    fact_id=fact_id,
                    source_field=source_field,
                    offending_text=fact_text[:160],
                )
                break
        normalized_fact_keys.add(fact_key)

    for item in assumptions:
        conf = float(item.get("confidence") or 0.0)
        based = list(item.get("based_on_fact_ids") or [])
        confidence_label = str(item.get("confidence_label") or "").strip().lower()
        if str(item.get("assumption_kind") or "").strip() != "inferred_hypothesis":
            codes.append("assumption_kind_invalid")
            _append_detail(
                details,
                "assumption_kind_invalid",
                offending_text=str(item.get("text") or "")[:160],
            )
            break
        if confidence_label not in HOOK_CONFIDENCE_VALUES:
            codes.append("assumption_confidence_label_invalid")
            _append_detail(
                details,
                "assumption_confidence_label_invalid",
                offending_text=str(item.get("text") or "")[:160],
            )
            break
        if conf > 0.8 and len(based) == 0:
            codes.append("assumption_high_confidence_no_grounding")
            _append_detail(
                details,
                "assumption_high_confidence_no_grounding",
                offending_text=str(item.get("text") or "")[:160],
                available_fact_ids=based,
            )
            break
        if confidence_label == "high" and len(based) < 2:
            codes.append("assumption_high_confidence_insufficient_facts")
            _append_detail(
                details,
                "assumption_high_confidence_insufficient_facts",
                offending_text=str(item.get("text") or "")[:160],
                available_fact_ids=based,
            )
            break
        if _is_placeholder_input_text(item.get("text")):
            codes.append("assumption_placeholder_text")
            _append_detail(
                details,
                "assumption_placeholder_text",
                offending_text=str(item.get("text") or "")[:160],
            )
            break

    source_lower = source_text.lower()
    for fact in facts:
        text = str(fact.get("text") or "").lower()
        if any(marker in text for marker in UNGROUNDED_PERSONALIZATION_MARKERS) and text not in source_lower:
            codes.append("fact_contains_ungrounded_behavior_claim")
            _append_detail(
                details,
                "fact_contains_ungrounded_behavior_claim",
                fact_id=str(fact.get("fact_id") or ""),
                offending_text=str(fact.get("text") or "")[:160],
            )
            break

    if source_payload:
        source_field_map = _source_field_value_map(source_payload)
        source_tokens: set[str] = set()
        for fragment in _flatten_input_text(list(source_field_map.values())):
            source_tokens.update(_grounding_tokens(fragment))
        fact_ids = {str(fact.get("fact_id") or "").strip() for fact in facts}
        for hook in hooks:
            hook_text = str(hook.get("hook_text") or "").strip()
            hook_id = str(hook.get("hook_id") or "").strip()
            supported = hook_supported_fact_ids(hook)
            seller_ids = hook_seller_fact_ids(hook)

            if any(
                _is_placeholder_input_text(hook.get(field))
                for field in ("grounded_observation", "inferred_relevance", "hook_text")
            ) or (_is_placeholder_input_text(hook.get("seller_support")) and str(hook.get("seller_support") or "").strip()):
                codes.append("hook_placeholder_text")
                _append_detail(
                    details,
                    "hook_placeholder_text",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                )
                break
            if not supported or any(item not in fact_ids for item in supported):
                codes.append("hook_unknown_fact_id")
                _append_detail(
                    details,
                    "hook_unknown_fact_id",
                    hook_id=hook_id,
                    available_fact_ids=supported,
                    offending_text=hook_text[:160],
                )
                break
            if any(item not in fact_ids for item in seller_ids):
                codes.append("hook_unknown_seller_fact_id")
                _append_detail(
                    details,
                    "hook_unknown_seller_fact_id",
                    hook_id=hook_id,
                    available_fact_ids=seller_ids,
                    offending_text=hook_text[:160],
                )
                break
            if str(hook.get("confidence_level") or "").strip().lower() not in HOOK_CONFIDENCE_VALUES:
                codes.append("hook_confidence_level_invalid")
                _append_detail(
                    details,
                    "hook_confidence_level_invalid",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                )
                break
            if str(hook.get("evidence_strength") or "").strip().lower() not in HOOK_EVIDENCE_VALUES:
                codes.append("hook_evidence_strength_invalid")
                _append_detail(
                    details,
                    "hook_evidence_strength_invalid",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                )
                break
            if str(hook.get("seller_support") or "").strip() and not seller_ids:
                codes.append("hook_seller_support_missing_fact_id")
                _append_detail(
                    details,
                    "hook_seller_support_missing_fact_id",
                    hook_id=hook_id,
                    offending_text=str(hook.get("seller_support") or "")[:160],
                )
                break
            if seller_fact_kinds(hook, fact_map) - {"seller_context", "seller_proof"}:
                codes.append("hook_seller_fact_id_not_seller_side")
                _append_detail(
                    details,
                    "hook_seller_fact_id_not_seller_side",
                    hook_id=hook_id,
                    available_fact_ids=seller_ids,
                    offending_text=str(hook.get("seller_support") or hook_text)[:160],
                )
                break
            posture = hook_support_posture(hook, fact_map, contaminated_fact_ids=contaminated_fact_ids)
            risk_flags = [str(item or "").strip() for item in (hook.get("risk_flags") or []) if str(item or "").strip()]
            if any(flag not in risk_flags for flag in posture["required_risk_flags"]):
                codes.append("hook_missing_seller_proof_gap")
                _append_detail(
                    details,
                    "hook_missing_seller_proof_gap",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                )
                break
            if hook_is_prospect_as_proof(hook, fact_map):
                codes.append("hook_prospect_as_proof")
                _append_detail(
                    details,
                    "hook_prospect_as_proof",
                    claim_type="prospect_as_proof",
                    hook_id=hook_id,
                    offending_text=str(hook.get("seller_support") or hook_text)[:160],
                    available_fact_ids=supported,
                    actual_evidence_kinds=sorted(seller_fact_kinds(hook, fact_map) or {"prospect_context"}),
                    required_evidence_kind="seller_context_or_seller_proof",
                )
                break
            if posture["has_contamination_tainted_support"]:
                codes.append("hook_contaminated_research")
                _append_detail(
                    details,
                    "hook_contaminated_research",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported,
                )
                break
            if CONFIDENCE_LEVEL_ORDER.get(hook_confidence_level(hook), 0) > CONFIDENCE_LEVEL_ORDER.get(posture["max_confidence_level"], 0):
                codes.append("hook_high_confidence_without_seller_proof")
                _append_detail(
                    details,
                    "hook_high_confidence_without_seller_proof",
                    claim_type="signal_strength_honest",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported + seller_ids,
                    actual_evidence_kinds=sorted(posture["seller_kinds"]),
                    required_evidence_kind="seller_proof",
                )
                break
            if EVIDENCE_STRENGTH_ORDER.get(hook_evidence_strength(hook), 0) > EVIDENCE_STRENGTH_ORDER.get(posture["max_evidence_strength"], 0):
                codes.append("hook_strong_evidence_without_seller_proof")
                _append_detail(
                    details,
                    "hook_strong_evidence_without_seller_proof",
                    claim_type="signal_strength_honest",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported + seller_ids,
                    actual_evidence_kinds=sorted(posture["seller_kinds"]),
                    required_evidence_kind="seller_proof",
                )
                break
            if hook_requires_grounded_research(hook) and not posture["supports_initiative_or_trigger"]:
                codes.append("hook_unsupported_recency_or_initiative")
                _append_detail(
                    details,
                    "hook_unsupported_recency_or_initiative",
                    claim_type="unsupported_initiative" if hook_mentions_initiative(hook) else "unsupported_recency",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported,
                    actual_evidence_kinds=["research_text"] if posture["has_contamination_tainted_support"] else [],
                    required_evidence_kind="research_text",
                )
                break
            if hook_has_strong_claim_language(hook) and not posture["has_explicit_seller_proof"]:
                codes.append("hook_claim_too_strong_for_evidence")
                _append_detail(
                    details,
                    "hook_claim_too_strong_for_evidence",
                    claim_type="signal_strength_honest",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported + seller_ids,
                    actual_evidence_kinds=sorted(posture["seller_kinds"] or {"prospect_context"}),
                    required_evidence_kind="seller_proof",
                )
                break

        persona_cues = dict(brief.get("persona_cues") or {})
        persona_values: list[Any] = [persona_cues.get("notes")]
        for key in ("likely_kpis", "likely_initiatives", "day_to_day", "tools_stack"):
            persona_values.extend(list(persona_cues.get(key) or []))
        if _has_placeholder_leakage(persona_values):
            codes.append("persona_placeholder_text")

        if source_tokens:
            for fact in facts:
                fact_text = str(fact.get("text") or "").strip()
                if _is_placeholder_input_text(fact_text):
                    continue
                tokens = _grounding_tokens(fact_text)
                if tokens and tokens.isdisjoint(source_tokens):
                    codes.append("fact_not_grounded_in_input")
                    _append_detail(
                        details,
                        "fact_not_grounded_in_input",
                        fact_id=str(fact.get("fact_id") or ""),
                        source_field=str(fact.get("source_field") or "").strip().lower(),
                        offending_text=fact_text[:160],
                    )
                    break

    unsupported_recency_present = any(
        hook_mentions_recency(hook) and not hook_support_posture(hook, fact_map, contaminated_fact_ids=contaminated_fact_ids)["supports_initiative_or_trigger"]
        for hook in hooks
    )
    unsupported_initiative_present = any(
        hook_mentions_initiative(hook) and not hook_support_posture(hook, fact_map, contaminated_fact_ids=contaminated_fact_ids)["supports_initiative_or_trigger"]
        for hook in hooks
    )

    overreach_risk = str(brief_quality.get("overreach_risk") or "").strip().lower()
    if overreach_risk not in OVERREACH_RISK_VALUES:
        codes.append("brief_quality_overreach_risk_invalid")
    if not signal_strength_matches(brief, source_text=source_text):
        codes.append("brief_quality_signal_strength_mismatch")
    if unsupported_recency_present and "unsupported_recency" not in prohibited_overreach:
        codes.append("prohibited_overreach_missing_recency")
    if unsupported_initiative_present and "unsupported_initiative" not in prohibited_overreach:
        codes.append("prohibited_overreach_missing_initiative")
    if any(hook_is_prospect_as_proof(hook, fact_map) for hook in hooks) and "prospect_as_proof" not in prohibited_overreach:
        codes.append("prohibited_overreach_missing_prospect_as_proof")

    _codes_or_raise(codes, details=details)


def validate_fit_map(fit_map: dict[str, Any], messaging_brief: dict[str, Any]) -> None:
    codes: list[str] = []
    hook_ids = {str(item.get("hook_id")) for item in messaging_brief.get("hooks") or []}
    fact_ids = {str(item.get("fact_id")) for item in messaging_brief.get("facts_from_input") or []}

    for hyp in fit_map.get("hypotheses") or []:
        if str(hyp.get("selected_hook_id")) not in hook_ids:
            codes.append("fit_unknown_hook_id")
            break
        supporting = list(hyp.get("supporting_fact_ids") or [])
        if not supporting:
            codes.append("fit_missing_supporting_facts")
            break
        if any(str(fid) not in fact_ids for fid in supporting):
            codes.append("fit_unknown_supporting_fact_id")
            break

    _codes_or_raise(codes)


def validate_angle_set(angle_set: dict[str, Any], messaging_brief: dict[str, Any], fit_map: dict[str, Any]) -> None:
    codes: list[str] = []
    angles = list(angle_set.get("angles") or [])
    if len(angles) < 3:
        codes.append("angle_set_too_small")
    hook_ids = {str(item.get("hook_id")) for item in messaging_brief.get("hooks") or []}
    hyp_ids = {str(item.get("fit_hypothesis_id")) for item in fit_map.get("hypotheses") or []}
    for angle in angles:
        if str(angle.get("selected_hook_id")) not in hook_ids:
            codes.append("angle_unknown_hook_id")
            break
        if str(angle.get("selected_fit_hypothesis_id")) not in hyp_ids:
            codes.append("angle_unknown_fit_hypothesis_id")
            break
    _codes_or_raise(codes)


def validate_message_atoms(
    atoms: dict[str, Any],
    *,
    preset_id: str,
    cta_final_line: str,
    messaging_brief: dict[str, Any],
    selected_angle: dict[str, Any],
    preset_contract: dict[str, Any],
    forbidden_patterns: list[str],
    budget_plan: dict[str, Any],
) -> None:
    codes: list[str] = []
    details: list[dict[str, Any]] = []
    facts = [item for item in (messaging_brief.get("facts_from_input") or []) if isinstance(item, dict)]
    seller_proof_facts = [fact for fact in facts if canonical_fact_kind(str(fact.get("source_field") or "")) == "seller_proof"]
    seller_proof_texts = [str(fact.get("text") or "").strip() for fact in seller_proof_facts if str(fact.get("text") or "").strip()]
    normalized_atoms = {
        "preset_id": str(atoms.get("preset_id") or "").strip(),
        "selected_angle_id": str(atoms.get("selected_angle_id") or "").strip(),
        "used_hook_ids": [str(item or "").strip() for item in (atoms.get("used_hook_ids") or []) if str(item or "").strip()],
        "opener_atom": str(atoms.get("opener_atom") or "").strip(),
        "value_atom": str(atoms.get("value_atom") or "").strip(),
        "proof_atom": str(atoms.get("proof_atom") or "").strip(),
        "cta_atom": str(atoms.get("cta_atom") or "").strip(),
        "cta_intent": str(atoms.get("cta_intent") or "").strip(),
        "required_cta_line": str(atoms.get("required_cta_line") or "").strip(),
        "target_word_budget": int(atoms.get("target_word_budget") or 0),
        "target_sentence_budget": int(atoms.get("target_sentence_budget") or 0),
    }

    if normalized_atoms["preset_id"] != str(preset_id or "").strip():
        codes.append("atoms_preset_mismatch")
        _append_detail(
            details,
            "atoms_preset_mismatch",
            offending_text=normalized_atoms["preset_id"],
            expected_preset_id=str(preset_id or "").strip(),
        )

    expected_angle_id = str(selected_angle.get("angle_id") or "").strip()
    if normalized_atoms["selected_angle_id"] != expected_angle_id:
        codes.append("atoms_selected_angle_mismatch")
        _append_detail(
            details,
            "atoms_selected_angle_mismatch",
            offending_text=normalized_atoms["selected_angle_id"],
            expected_angle_id=expected_angle_id,
        )

    cta_status = cta_alignment_status(candidate=normalized_atoms["cta_atom"], required_cta_line=cta_final_line)
    if normalized_atoms["required_cta_line"] != str(cta_final_line or "").strip():
        codes.append("atoms_required_cta_mismatch")
        _append_detail(
            details,
            "atoms_required_cta_mismatch",
            offending_text=normalized_atoms["required_cta_line"],
            expected_cta=str(cta_final_line or "").strip(),
        )
    if cta_status != "aligned":
        codes.append("atoms_cta_mismatch")
        _append_detail(
            details,
            "atoms_cta_mismatch",
            offending_text=normalized_atoms["cta_atom"],
            cta_alignment_status=cta_status,
            expected_cta=str(cta_final_line or "").strip(),
        )

    used_hooks = normalized_atoms["used_hook_ids"]
    if len(used_hooks) < 1:
        codes.append("atoms_missing_used_hook_ids")
        _append_detail(details, "atoms_missing_used_hook_ids", offending_text="")
    if len(set(used_hooks)) != len(used_hooks):
        codes.append("atoms_duplicate_used_hook_id")
        _append_detail(details, "atoms_duplicate_used_hook_id", available_fact_ids=used_hooks)
    hook_ids = {
        str(item.get("hook_id") or "").strip()
        for item in (messaging_brief.get("hooks") or [])
        if isinstance(item, dict)
    }
    if any(hook_id and hook_id not in hook_ids for hook_id in used_hooks):
        codes.append("atoms_unknown_hook_id")
        _append_detail(details, "atoms_unknown_hook_id", available_fact_ids=used_hooks)
    selected_hook_id = str(selected_angle.get("selected_hook_id") or "").strip()
    if selected_hook_id and selected_hook_id not in used_hooks:
        codes.append("atoms_selected_hook_not_preserved")
        _append_detail(
            details,
            "atoms_selected_hook_not_preserved",
            offending_text=selected_hook_id,
            available_fact_ids=used_hooks,
        )

    opener = normalized_atoms["opener_atom"].lower()
    for pattern in forbidden_patterns:
        token = str(pattern or "").strip().lower()
        if token and token in opener:
            codes.append("atoms_forbidden_opener_pattern")
            _append_detail(details, "atoms_forbidden_opener_pattern", offending_text=token)
            break

    proof_atom = normalized_atoms["proof_atom"]
    if proof_atom:
        if not seller_proof_texts:
            codes.append("atoms_proof_without_seller_proof")
            _append_detail(
                details,
                "atoms_proof_without_seller_proof",
                offending_text=proof_atom[:160],
                required_evidence_kind="seller_proof",
            )
        else:
            proof_tokens = _grounding_tokens(proof_atom)
            seller_proof_tokens: set[str] = set()
            seller_numeric_tokens: set[str] = set()
            for seller_text in seller_proof_texts:
                seller_proof_tokens.update(_grounding_tokens(seller_text))
                seller_numeric_tokens.update(_numeric_tokens(seller_text))
            overlap = proof_tokens & seller_proof_tokens
            numeric_tokens = _numeric_tokens(proof_atom)
            if len(overlap) < 2 or (numeric_tokens and numeric_tokens.isdisjoint(seller_numeric_tokens)):
                codes.append("atoms_proof_not_grounded_in_seller_proof")
                _append_detail(
                    details,
                    "atoms_proof_not_grounded_in_seller_proof",
                    offending_text=proof_atom[:160],
                    actual_evidence_kinds=["seller_proof"],
                    required_evidence_kind="seller_proof",
                )

    atom_fields = ("opener_atom", "value_atom", "proof_atom", "cta_atom")
    duplicate_map: dict[str, str] = {}
    for field in atom_fields:
        text = normalized_atoms[field]
        if not text:
            continue
        lowered = text.lower()
        if lowered in duplicate_map:
            codes.append("atoms_duplicate_or_conflicting")
            _append_detail(
                details,
                "atoms_duplicate_or_conflicting",
                offending_text=text[:160],
                duplicate_field=duplicate_map[lowered],
                duplicate_with=field,
            )
            break
        duplicate_map[lowered] = field

    expected_budget = plan_budget(
        preset_id=str(preset_id or "").strip(),
        preset_contract=preset_contract,
        selected_angle=selected_angle,
        message_atoms=normalized_atoms,
    )
    if normalized_atoms["target_word_budget"] != int(expected_budget.get("target_total_words") or 0):
        codes.append("atoms_target_word_budget_mismatch")
        _append_detail(
            details,
            "atoms_target_word_budget_mismatch",
            offending_text=str(normalized_atoms["target_word_budget"]),
            expected_target=int(expected_budget.get("target_total_words") or 0),
        )
    if normalized_atoms["target_sentence_budget"] != int(expected_budget.get("target_sentence_count") or 0):
        codes.append("atoms_target_sentence_budget_mismatch")
        _append_detail(
            details,
            "atoms_target_sentence_budget_mismatch",
            offending_text=str(normalized_atoms["target_sentence_budget"]),
            expected_target=int(expected_budget.get("target_sentence_count") or 0),
        )
    if int(expected_budget.get("target_total_words") or 0) != int(budget_plan.get("target_total_words") or 0):
        codes.append("atoms_budget_seed_mismatch")
        _append_detail(
            details,
            "atoms_budget_seed_mismatch",
            offending_text=str(normalized_atoms["target_word_budget"]),
            expected_target=int(budget_plan.get("target_total_words") or 0),
        )
    if str(expected_budget.get("feasibility_status") or "") == "infeasible":
        codes.append("atoms_budget_infeasible")
        _append_detail(
            details,
            "atoms_budget_infeasible",
            offending_text=str(expected_budget.get("feasibility_reason") or ""),
        )

    words_by_atom = atom_word_counts(normalized_atoms)
    if words_by_atom.get("cta_atom", 0) >= int(expected_budget.get("target_total_words") or 0):
        codes.append("atoms_budget_infeasible")
        _append_detail(
            details,
            "atoms_budget_infeasible",
            offending_text="cta_atom_consumes_budget",
        )

    _codes_or_raise(list(dict.fromkeys(codes)), details=details)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _paragraphs(text: str) -> list[str]:
    return [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if chunk.strip()]


def _is_non_generic_opener(opener_line: str) -> bool:
    lowered = opener_line.lower().strip()
    generic = [
        "hope this finds you well",
        "wanted to reach out",
        "quick note",
        "just checking in",
        "hi there",
    ]
    return bool(lowered) and not any(token in lowered for token in generic)


def _length_band(length: str) -> tuple[int, int]:
    key = str(length or "medium").strip().lower()
    if key == "short":
        return (40, 80)
    if key == "long":
        return (140, 220)
    return (80, 140)


def validation_code_set(codes: list[str]) -> set[str]:
    return {str(code or "").strip() for code in codes if str(code or "").strip()}


def dominant_validation_code(codes: list[str]) -> str | None:
    for code in codes:
        token = str(code or "").strip()
        if token:
            return token
    return None


def salvage_eligible_validation_codes(codes: list[str]) -> bool:
    return validation_code_set(codes) == {"word_count_out_of_band"}


def validate_email_draft(
    draft: dict[str, Any],
    *,
    brief: dict[str, Any],
    cta_final_line: str,
    sliders: dict[str, Any],
    preset_contract: dict[str, Any] | None = None,
    budget_plan: dict[str, Any] | None = None,
    personalization_threshold: float = 0.65,
) -> list[str]:
    codes: list[str] = []
    subject = str(draft.get("subject") or "").strip()
    body = str(draft.get("body") or "").strip()
    used_hook_ids = list(draft.get("used_hook_ids") or [])

    if len(subject) > 70:
        codes.append("subject_too_long")

    cta = str(cta_final_line or "").strip()
    if cta:
        if not body.endswith(cta):
            codes.append("cta_not_final_line")
        if body.count(cta) > 1:
            codes.append("duplicate_cta_line")

    lower_body = body.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower_body or phrase in subject.lower():
            codes.append("banned_phrase")
            break

    facts_text = "\n".join(str(item.get("text") or "").lower() for item in brief.get("facts_from_input") or [])
    for marker in UNGROUNDED_PERSONALIZATION_MARKERS:
        if marker in lower_body and marker not in facts_text:
            codes.append("ungrounded_personalization_claim")
            break

    paras = _paragraphs(body)
    for i in range(len(paras)):
        for j in range(i + 1, len(paras)):
            if SequenceMatcher(a=paras[i].lower(), b=paras[j].lower()).ratio() >= 0.85:
                codes.append("repetition_detected")
                break
        if "repetition_detected" in codes:
            break

    contract = dict(preset_contract or {})
    plan = dict(budget_plan or {})
    hard_word_range = dict(contract.get("hard_word_range") or {})
    sentence_guidance = dict(contract.get("sentence_count_guidance") or {})

    length = str(sliders.get("length") or "medium")
    min_words, max_words = _length_band(length)
    if isinstance(hard_word_range.get("min"), int) and isinstance(hard_word_range.get("max"), int):
        min_words = int(hard_word_range["min"])
        max_words = int(hard_word_range["max"])
    if isinstance(plan.get("allowed_min_words"), int) and isinstance(plan.get("allowed_max_words"), int):
        min_words = int(plan["allowed_min_words"])
        max_words = int(plan["allowed_max_words"])
    wc = _word_count(body)
    if wc < min_words or wc > max_words:
        codes.append("word_count_out_of_band")

    hard_sentence_max = sentence_guidance.get("hard_max")
    if isinstance(plan.get("allowed_max_sentences"), int):
        hard_sentence_max = int(plan["allowed_max_sentences"])
    if isinstance(hard_sentence_max, int) and contract_sentence_count(body) > hard_sentence_max:
        codes.append("too_many_sentences_for_preset")

    tone_marker = float(sliders.get("framing", 0.5))
    if tone_marker >= personalization_threshold:
        opener = str(body.splitlines()[0] if body else "")
        if len(used_hook_ids) == 0:
            codes.append("personalization_missing_used_hook")
        if not _is_non_generic_opener(opener):
            codes.append("personalization_generic_opener")

    return codes


_QA_ALLOWED_ISSUE_TYPES = {
    "credibility",
    "specificity",
    "structure",
    "spam_risk",
    "personalization",
    "length",
    "cta",
    "grammar",
    "tone",
    "clarity",
    "word_count_out_of_band",
    "opener_too_soft_for_preset",
    "proof_density_too_low",
    "too_many_sentences_for_preset",
    "tone_mismatch_for_preset",
    "cta_not_in_expected_form",
    "other",
}


def _normalize_issue_code(value: Any) -> str:
    text = re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
    return text or "other"


def _normalize_issue_type(issue_code: str, raw_type: Any) -> str:
    issue_type = str(raw_type or "").strip()
    if issue_type in _QA_ALLOWED_ISSUE_TYPES:
        return issue_type
    if issue_code in _QA_ALLOWED_ISSUE_TYPES:
        return issue_code
    if issue_code.startswith("cta"):
        return "cta"
    if "proof" in issue_code:
        return "credibility"
    if "personal" in issue_code or "hook" in issue_code:
        return "personalization"
    if "tone" in issue_code:
        return "tone"
    if "word_count" in issue_code or "sentence" in issue_code or "length" in issue_code:
        return "length"
    if "spam" in issue_code or "banned" in issue_code:
        return "spam_risk"
    return "other"


def _qa_draft_blob(draft: dict[str, Any] | None) -> str:
    if not isinstance(draft, dict):
        return ""
    subject = str(draft.get("subject") or "").strip()
    body = str(draft.get("body") or "").strip()
    return "\n".join(part for part in (subject, body) if part)


def _strip_wrapping_quotes(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text


def _normalize_evidence_quote(issue: dict[str, Any], draft_blob: str) -> str:
    candidates = [issue.get("evidence_quote")]
    evidence = issue.get("evidence")
    if isinstance(evidence, list):
        candidates.extend(evidence)
    for candidate in candidates:
        text = str(candidate or "").strip()
        if not text:
            continue
        if text in draft_blob:
            return text
        unquoted = _strip_wrapping_quotes(text)
        if unquoted and unquoted in draft_blob:
            return unquoted
    return ""


def _preserve_instruction(locked_cta: str) -> str:
    if locked_cta:
        return f'Keep the locked CTA text "{locked_cta}" unchanged and leave unrelated grounded sentences untouched.'
    return "Leave unrelated grounded sentences untouched."


def _default_issue_explanation(issue_code: str, evidence_quote: str) -> str:
    if issue_code.startswith("cta"):
        return f'The quoted text breaks the locked CTA contract or its final-line placement: "{evidence_quote}".'
    if issue_code in {"word_count_out_of_band", "too_many_sentences_for_preset"}:
        return "The draft is outside the preset word or sentence contract."
    if "proof" in issue_code or "unsupported" in issue_code or "ground" in issue_code:
        return f'The quoted text introduces proof or factual framing that is not grounded strongly enough: "{evidence_quote}".'
    return f'The quoted text is the specific failing span that should be revised: "{evidence_quote}".'


def _default_expected_effect(issue_code: str) -> str:
    if issue_code.startswith("cta"):
        return "Restore exact locked CTA fidelity with one final-line CTA only."
    if issue_code in {"word_count_out_of_band", "too_many_sentences_for_preset"}:
        return "Bring the draft back inside the preset word and sentence band."
    if "proof" in issue_code or "unsupported" in issue_code or "ground" in issue_code:
        return "Remove unsupported material and keep only grounded claims."
    if "tone" in issue_code:
        return "Bring the draft back to the preset tone without adding claims."
    return "Resolve the targeted issue while preserving grounded copy elsewhere."


def _default_fix_instruction(issue_code: str, target: str, locked_cta: str) -> str:
    if issue_code.startswith("cta"):
        if locked_cta:
            return (
                f'Keep the locked CTA text "{locked_cta}" unchanged; make it the only final line and remove any extra '
                "CTA or question wording around it."
            )
        return "Keep the CTA text unchanged and make it the only final line."
    if issue_code in {"word_count_out_of_band", "too_many_sentences_for_preset"}:
        return (
            f"Edit only {target} to fit the preset word and sentence targets; shorten or remove the least essential "
            "supported wording and leave the locked CTA unchanged."
        )
    if "proof" in issue_code or "unsupported" in issue_code or "ground" in issue_code:
        return (
            f"Delete or narrow {target} so it only uses seller proof or prospect facts explicitly supported by the "
            "brief; do not invent replacement proof."
        )
    return (
        f"Replace {target} with a grounded alternative tied to the selected hook and brief facts; leave unrelated "
        "sentences unchanged."
    )


def _normalize_fix_instruction(issue_code: str, raw_fix: Any, target: str, locked_cta: str) -> str:
    fix_instruction = str(raw_fix or "").strip()
    if issue_code.startswith("cta"):
        return _default_fix_instruction(issue_code, target, locked_cta)
    if not fix_instruction:
        return _default_fix_instruction(issue_code, target, locked_cta)
    return fix_instruction


def _normalize_qa_issue(issue: dict[str, Any], *, draft_blob: str, locked_cta: str) -> dict[str, Any] | None:
    if not isinstance(issue, dict):
        return None
    issue_code = _normalize_issue_code(issue.get("issue_code") or issue.get("type") or "other")
    evidence_quote = _normalize_evidence_quote(issue, draft_blob)
    if not evidence_quote:
        return None
    target = str(issue.get("offending_span_or_target_section") or "").strip() or evidence_quote
    severity = str(issue.get("severity") or "medium").strip().lower()
    if severity not in {"low", "medium", "high"}:
        severity = "medium"
    why_it_fails = str(issue.get("why_it_fails") or "").strip() or _default_issue_explanation(issue_code, evidence_quote)
    expected_effect = str(issue.get("expected_effect") or "").strip() or _default_expected_effect(issue_code)
    normalized = {
        "issue_code": issue_code,
        "type": _normalize_issue_type(issue_code, issue.get("type")),
        "severity": severity,
        "offending_span_or_target_section": target,
        "evidence_quote": evidence_quote,
        "why_it_fails": why_it_fails,
        "fix_instruction": _normalize_fix_instruction(issue_code, issue.get("fix_instruction"), target, locked_cta),
        "expected_effect": expected_effect,
        "evidence": [evidence_quote],
    }
    return normalized


def _issue_to_rewrite_action(issue: dict[str, Any], *, locked_cta: str) -> dict[str, Any]:
    return {
        "issue_code": str(issue.get("issue_code") or "other"),
        "target": str(issue.get("offending_span_or_target_section") or "body"),
        "action": str(issue.get("fix_instruction") or ""),
        "replacement_guidance": str(issue.get("fix_instruction") or ""),
        "preserve": _preserve_instruction(locked_cta),
        "expected_effect": str(issue.get("expected_effect") or _default_expected_effect(str(issue.get("issue_code") or "other"))),
    }


def _normalize_rewrite_plan(
    raw_plan: Any,
    *,
    issues: list[dict[str, Any]],
    locked_cta: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    raw_items = raw_plan if isinstance(raw_plan, list) else []
    for index, raw_item in enumerate(raw_items):
        issue = issues[index] if index < len(issues) else (issues[0] if issues else None)
        if isinstance(raw_item, dict):
            issue_code = _normalize_issue_code(raw_item.get("issue_code") or raw_item.get("type") or (issue or {}).get("issue_code") or "other")
            target = str(raw_item.get("target") or raw_item.get("offending_span_or_target_section") or (issue or {}).get("offending_span_or_target_section") or "").strip()
            action = str(raw_item.get("action") or "").strip()
            replacement_guidance = str(raw_item.get("replacement_guidance") or raw_item.get("fix_instruction") or (issue or {}).get("fix_instruction") or "").strip()
            preserve = str(raw_item.get("preserve") or "").strip() or _preserve_instruction(locked_cta)
            expected_effect = str(raw_item.get("expected_effect") or (issue or {}).get("expected_effect") or "").strip() or _default_expected_effect(issue_code)
            if issue_code and target and action and replacement_guidance and preserve and expected_effect:
                normalized.append(
                    {
                        "issue_code": issue_code,
                        "target": target,
                        "action": action,
                        "replacement_guidance": replacement_guidance,
                        "preserve": preserve,
                        "expected_effect": expected_effect,
                    }
                )
            continue

        text = str(raw_item or "").strip()
        if not text or issue is None:
            continue
        normalized.append(
            {
                "issue_code": str(issue.get("issue_code") or "other"),
                "target": str(issue.get("offending_span_or_target_section") or "body"),
                "action": text,
                "replacement_guidance": str(issue.get("fix_instruction") or text),
                "preserve": _preserve_instruction(locked_cta),
                "expected_effect": str(issue.get("expected_effect") or _default_expected_effect(str(issue.get("issue_code") or "other"))),
            }
        )

    if normalized:
        return normalized[:8]

    return [
        _issue_to_rewrite_action(issue, locked_cta=locked_cta)
        for issue in issues
        if str(issue.get("severity") or "").lower() in {"high", "medium"}
    ][:8]


def normalize_qa_report(
    qa_report: dict[str, Any],
    *,
    draft: dict[str, Any] | None = None,
    locked_cta: str | None = None,
) -> dict[str, Any]:
    report = dict(qa_report or {})
    draft_blob = _qa_draft_blob(draft)
    normalized_issues = [
        normalized
        for normalized in (
            _normalize_qa_issue(issue, draft_blob=draft_blob, locked_cta=str(locked_cta or "").strip())
            for issue in (report.get("issues") or [])
        )
        if normalized is not None
    ]
    has_high = any(str(item.get("severity") or "").lower() == "high" for item in normalized_issues)
    pass_rewrite_needed = bool(report.get("pass_rewrite_needed")) or has_high
    if not normalized_issues:
        pass_rewrite_needed = False

    report["version"] = str(report.get("version") or "1.0")
    report["issues"] = normalized_issues
    report["risk_flags"] = _normalized_string_list(report.get("risk_flags") or [])
    report["pass_rewrite_needed"] = pass_rewrite_needed
    report["rewrite_plan"] = (
        _normalize_rewrite_plan(report.get("rewrite_plan"), issues=normalized_issues, locked_cta=str(locked_cta or "").strip())
        if pass_rewrite_needed
        else []
    )
    return report


def _qa_body_sentences(draft: dict[str, Any] | None) -> list[str]:
    body = str((draft or {}).get("body") or "").strip()
    if not body:
        return []
    collapsed = re.sub(r"\s+", " ", body.replace("\n", " ")).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", collapsed) if part.strip()]


def _qa_last_nonempty_line(draft: dict[str, Any] | None) -> str:
    lines = [line.strip() for line in str((draft or {}).get("body") or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _first_body_sentence(draft: dict[str, Any] | None) -> str:
    sentences = _qa_body_sentences(draft)
    return sentences[0] if sentences else str((draft or {}).get("body") or "").strip()


def _find_sentence_with_token(draft: dict[str, Any] | None, tokens: list[str]) -> str:
    lowered_tokens = [token.lower() for token in tokens if token]
    for sentence in _qa_body_sentences(draft):
        lowered = sentence.lower()
        if any(token in lowered for token in lowered_tokens):
            return sentence
    return _first_body_sentence(draft)


def _opener_clause_counts(draft: dict[str, Any] | None) -> tuple[int, int]:
    opener = _first_body_sentence(draft)
    comma_count = opener.count(",")
    connector_count = len(re.findall(r"\b(which|that|because|so|and)\b", opener.lower()))
    return comma_count, connector_count


def _validation_issue_dict(
    *,
    issue_code: str,
    severity: str,
    target: str,
    evidence_quote: str,
    why_it_fails: str,
    fix_instruction: str,
    expected_effect: str,
) -> dict[str, Any]:
    normalized_issue_code = _normalize_issue_code(issue_code)
    normalized_target = str(target or "").strip() or "body"
    normalized_quote = str(evidence_quote or "").strip() or normalized_target
    return {
        "issue_code": normalized_issue_code,
        "type": _normalize_issue_type(normalized_issue_code, None),
        "severity": severity,
        "offending_span_or_target_section": normalized_target,
        "evidence_quote": normalized_quote,
        "why_it_fails": why_it_fails,
        "fix_instruction": fix_instruction,
        "expected_effect": expected_effect,
        "evidence": [normalized_quote],
    }


def _synthesized_issue_for_validation_code(
    code: str,
    *,
    draft: dict[str, Any] | None,
    locked_cta: str,
) -> dict[str, Any] | None:
    normalized_code = str(code or "").strip()
    subject = str((draft or {}).get("subject") or "").strip()

    if normalized_code == "subject_too_long" and subject:
        return _validation_issue_dict(
            issue_code="subject_too_long",
            severity="medium",
            target="subject",
            evidence_quote=subject,
            why_it_fails="The subject line is longer than the hard limit and needs a tighter phrasing.",
            fix_instruction="Trim the subject line only; keep the same grounded claim but remove extra words so it stays under 70 characters.",
            expected_effect="Bring the subject back inside the subject-length limit without changing the offer.",
        )

    if normalized_code == "word_count_out_of_band":
        sentence = _first_body_sentence(draft)
        return _validation_issue_dict(
            issue_code="word_count_out_of_band",
            severity="high",
            target="body before CTA",
            evidence_quote=sentence,
            why_it_fails="The body is outside the preset word band, so the draft needs one localized length correction.",
            fix_instruction="Expand only the body before the locked CTA by adding one grounded middle sentence tied to the selected hook; keep the CTA text unchanged.",
            expected_effect="Bring the draft back inside the preset word band while preserving the angle and CTA.",
        )

    if normalized_code == "too_many_sentences_for_preset":
        sentence = _first_body_sentence(draft)
        return _validation_issue_dict(
            issue_code="too_many_sentences_for_preset",
            severity="high",
            target="body before CTA",
            evidence_quote=sentence,
            why_it_fails="The draft uses too many sentences for the active preset contract.",
            fix_instruction="Compress the body before the locked CTA by merging or removing the least essential sentence; keep the CTA text unchanged.",
            expected_effect="Bring the draft back inside the preset sentence limit without changing the CTA.",
        )

    if normalized_code in {"cta_not_final_line", "duplicate_cta_line"}:
        evidence_quote = _qa_last_nonempty_line(draft) or locked_cta
        return _validation_issue_dict(
            issue_code="cta_not_in_expected_form",
            severity="high",
            target="final CTA line",
            evidence_quote=evidence_quote,
            why_it_fails="The CTA is not isolated as the one exact final line required by the contract.",
            fix_instruction=_default_fix_instruction("cta_not_in_expected_form", "final CTA line", locked_cta),
            expected_effect=_default_expected_effect("cta_not_in_expected_form"),
        )

    if normalized_code == "ungrounded_personalization_claim":
        sentence = _find_sentence_with_token(draft, list(UNGROUNDED_PERSONALIZATION_MARKERS))
        return _validation_issue_dict(
            issue_code="ungrounded_personalization_claim",
            severity="high",
            target=sentence or "opener sentence",
            evidence_quote=sentence or _first_body_sentence(draft),
            why_it_fails="The quoted personalization overstates prospect-specific context that is not grounded strongly enough.",
            fix_instruction="Replace only the quoted sentence with a narrower opener that stays inside supported role or company facts; do not add new proof.",
            expected_effect="Remove unsupported personalization while keeping the selected angle grounded.",
        )

    if normalized_code == "banned_phrase":
        sentence = _find_sentence_with_token(draft, BANNED_PHRASES)
        return _validation_issue_dict(
            issue_code="spam_risk",
            severity="high",
            target=sentence or "body sentence",
            evidence_quote=sentence or _first_body_sentence(draft),
            why_it_fails="The quoted line contains a banned outreach phrase.",
            fix_instruction="Replace only the quoted line with a grounded alternative that removes the banned phrase and keeps the rest of the draft unchanged.",
            expected_effect="Remove the banned phrase without changing the email structure or CTA.",
        )

    return None


def augment_qa_report_from_validation_codes(
    qa_report: dict[str, Any],
    *,
    draft: dict[str, Any] | None = None,
    locked_cta: str | None = None,
    validation_codes: list[str] | None = None,
) -> dict[str, Any]:
    report = dict(qa_report or {})
    normalized_codes = [str(code or "").strip() for code in (validation_codes or []) if str(code or "").strip()]
    if not normalized_codes:
        return report

    issues = [item for item in (report.get("issues") or []) if isinstance(item, dict)]
    existing_codes = {str(item.get("issue_code") or "").strip() for item in issues}
    for code in normalized_codes:
        synthesized = _synthesized_issue_for_validation_code(code, draft=draft, locked_cta=str(locked_cta or "").strip())
        if not synthesized:
            continue
        issue_code = str(synthesized.get("issue_code") or "").strip()
        if issue_code in existing_codes:
            continue
        issues.append(synthesized)
        existing_codes.add(issue_code)

    report["issues"] = issues
    if issues:
        report["pass_rewrite_needed"] = True
        report["rewrite_plan"] = _normalize_rewrite_plan(
            report.get("rewrite_plan"),
            issues=issues,
            locked_cta=str(locked_cta or "").strip(),
        )
    return report


def augment_qa_report_from_draft_heuristics(
    qa_report: dict[str, Any],
    *,
    draft: dict[str, Any] | None = None,
    locked_cta: str | None = None,
) -> dict[str, Any]:
    report = dict(qa_report or {})
    issues = [item for item in (report.get("issues") or []) if isinstance(item, dict)]
    if not draft:
        return report

    existing_codes = {str(item.get("issue_code") or "").strip() for item in issues}
    comma_count, connector_count = _opener_clause_counts(draft)
    if "opener_too_complex" not in existing_codes and (comma_count > 1 or connector_count > 1):
        opener = _first_body_sentence(draft)
        issues.append(
            _validation_issue_dict(
                issue_code="opener_too_complex",
                severity="medium",
                target="opener sentence",
                evidence_quote=opener,
                why_it_fails="The opener carries too many clauses, which weakens clarity and makes the first line feel generic.",
                fix_instruction="Replace only the opener sentence with a simpler single-clause opener tied to the same grounded hook; move any secondary detail into the next sentence and keep the locked CTA unchanged.",
                expected_effect="Make the opening line easier to scan while preserving the selected angle and grounded support.",
            )
        )

    report["issues"] = issues
    if issues:
        report["pass_rewrite_needed"] = True
        report["rewrite_plan"] = _normalize_rewrite_plan(
            report.get("rewrite_plan"),
            issues=issues,
            locked_cta=str(locked_cta or "").strip(),
        )
    return report
