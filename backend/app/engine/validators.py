from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .brief_honesty import (
    HOOK_CONFIDENCE_VALUES,
    HOOK_EVIDENCE_VALUES,
    OVERREACH_RISK_VALUES,
    canonical_fact_kind,
    compute_overreach_risk,
    fact_kind_counts,
    fact_map_by_id,
    hook_confidence_level,
    hook_evidence_strength,
    hook_has_seller_proof,
    hook_has_strong_claim_language,
    hook_is_prospect_as_proof,
    hook_mentions_initiative,
    hook_mentions_recency,
    hook_requires_grounded_research,
    hook_seller_fact_ids,
    hook_supported_fact_ids,
    normalize_text_key,
    seller_fact_kinds,
    signal_strength_matches,
)
from .research_state import has_meaningful_research, is_placeholder_fact_text, is_semantic_no_research, normalize_placeholder_text
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
    brief_quality = dict(brief.get("brief_quality") or {})
    prohibited_overreach = [str(item or "").strip().lower() for item in (brief.get("prohibited_overreach") or [])]
    details: list[dict[str, Any]] = []

    if len(facts) < 1:
        codes.append("brief_missing_facts")
    if len(hooks) < 1:
        codes.append("brief_missing_hooks")

    fact_map = fact_map_by_id(facts)
    normalized_fact_keys: set[tuple[str, str]] = set()

    for fact in facts:
        fact_id = str(fact.get("fact_id") or "").strip()
        fact_text = str(fact.get("text") or "").strip()
        source_field = str(fact.get("source_field") or "").strip().lower()
        fact_kind = str(fact.get("fact_kind") or "").strip().lower()
        expected_kind = canonical_fact_kind(source_field)

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

        if fact_kind != expected_kind:
            codes.append("fact_kind_mismatch")
            _append_detail(
                details,
                "fact_kind_mismatch",
                fact_id=fact_id,
                source_field=source_field,
                offending_text=fact_text[:160],
                required_evidence_kind=expected_kind,
                actual_evidence_kinds=[fact_kind] if fact_kind else [],
            )
            break

        fact_key = (fact_kind, normalize_text_key(fact_text))
        if fact_key in normalized_fact_keys and fact_kind != "cta":
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
            if hook_confidence_level(hook) == "high" and not hook_has_seller_proof(hook, fact_map):
                codes.append("hook_high_confidence_without_seller_proof")
                _append_detail(
                    details,
                    "hook_high_confidence_without_seller_proof",
                    claim_type="signal_strength_honest",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported + seller_ids,
                    actual_evidence_kinds=sorted(seller_fact_kinds(hook, fact_map)),
                    required_evidence_kind="seller_proof",
                )
                break
            if hook_evidence_strength(hook) == "strong" and not hook_has_seller_proof(hook, fact_map):
                codes.append("hook_strong_evidence_without_seller_proof")
                _append_detail(
                    details,
                    "hook_strong_evidence_without_seller_proof",
                    claim_type="signal_strength_honest",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported + seller_ids,
                    actual_evidence_kinds=sorted(seller_fact_kinds(hook, fact_map)),
                    required_evidence_kind="seller_proof",
                )
                break
            if hook_requires_grounded_research(hook) and not any(
                str((fact_map.get(fid) or {}).get("source_field") or "").strip().lower() == "research_text"
                for fid in supported
            ):
                codes.append("hook_unsupported_recency_or_initiative")
                _append_detail(
                    details,
                    "hook_unsupported_recency_or_initiative",
                    claim_type="unsupported_initiative" if hook_mentions_initiative(hook) else "unsupported_recency",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported,
                    actual_evidence_kinds=[],
                    required_evidence_kind="research_text",
                )
                break
            if hook_has_strong_claim_language(hook) and not hook_has_seller_proof(hook, fact_map):
                codes.append("hook_claim_too_strong_for_evidence")
                _append_detail(
                    details,
                    "hook_claim_too_strong_for_evidence",
                    claim_type="signal_strength_honest",
                    hook_id=hook_id,
                    offending_text=hook_text[:160],
                    available_fact_ids=supported + seller_ids,
                    actual_evidence_kinds=sorted(seller_fact_kinds(hook, fact_map) or {"prospect_context"}),
                    required_evidence_kind="seller_proof",
                )
                break

        persona_cues = dict(brief.get("persona_cues") or {})
        persona_values: list[Any] = [persona_cues.get("notes")]
        for key in ("likely_kpis", "likely_initiatives", "day_to_day", "tools_stack"):
            persona_values.extend(list(persona_cues.get(key) or []))
        if _has_placeholder_leakage(persona_values):
            codes.append("persona_placeholder_text")

        allowed_sources = [str(item or "").strip() for item in (brief.get("grounding_policy", {}).get("allowed_personalization_fact_sources") or [])]
        for source_field in allowed_sources:
            if source_field and source_field not in ALLOWED_STAGE_A_SOURCE_FIELDS:
                codes.append("grounding_policy_unknown_source_field")
                break
            if source_field and not _field_has_usable_signal(source_field_map.get(source_field)):
                codes.append("grounding_policy_uses_unusable_source_field")
                break

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

    if not brief_quality:
        codes.append("brief_missing_brief_quality")
    else:
        confidence_ceiling = float(brief_quality.get("confidence_ceiling") or 0.0)
        has_research = bool(brief_quality.get("has_research"))
        overreach_risk = str(brief_quality.get("overreach_risk") or "").strip().lower()
        kind_counts = fact_kind_counts(facts)
        grounded_fact_count = kind_counts["prospect_context"] + kind_counts["seller_context"] + kind_counts["seller_proof"]

        if confidence_ceiling < 0.0 or confidence_ceiling > 1.0:
            codes.append("brief_quality_confidence_ceiling_out_of_range")

        semantic_has_research = has_meaningful_research(source_text)
        if semantic_has_research != has_research:
            codes.append("brief_quality_has_research_mismatch")

        if int(brief_quality.get("fact_count") or 0) != len(facts):
            codes.append("brief_quality_fact_count_mismatch")
        if int(brief_quality.get("grounded_fact_count") or 0) != grounded_fact_count:
            codes.append("brief_quality_grounded_fact_count_mismatch")
        if int(brief_quality.get("prospect_context_fact_count") or 0) != kind_counts["prospect_context"]:
            codes.append("brief_quality_prospect_context_fact_count_mismatch")
        if int(brief_quality.get("seller_context_fact_count") or 0) != kind_counts["seller_context"]:
            codes.append("brief_quality_seller_context_fact_count_mismatch")
        if int(brief_quality.get("seller_proof_fact_count") or 0) != kind_counts["seller_proof"]:
            codes.append("brief_quality_seller_proof_fact_count_mismatch")
        if int(brief_quality.get("cta_fact_count") or 0) != kind_counts["cta"]:
            codes.append("brief_quality_cta_fact_count_mismatch")
        if str(brief_quality.get("signal_strength") or "").strip().lower() not in {"low", "medium", "high"}:
            codes.append("brief_quality_signal_strength_invalid")
        elif not signal_strength_matches(brief, source_text=source_text):
            codes.append("brief_quality_signal_strength_mismatch")
        if overreach_risk not in OVERREACH_RISK_VALUES:
            codes.append("brief_quality_overreach_risk_invalid")
        elif overreach_risk != compute_overreach_risk(brief):
            codes.append("brief_quality_overreach_risk_mismatch")

    unsupported_recency_present = any(
        hook_mentions_recency(hook)
        and not any(
            str((fact_map.get(fid) or {}).get("source_field") or "").strip().lower() == "research_text"
            for fid in hook_supported_fact_ids(hook)
        )
        for hook in hooks
    )
    unsupported_initiative_present = any(
        hook_mentions_initiative(hook)
        and not any(
            str((fact_map.get(fid) or {}).get("source_field") or "").strip().lower() == "research_text"
            for fid in hook_supported_fact_ids(hook)
        )
        for hook in hooks
    )

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


def validate_message_atoms(atoms: dict[str, Any], *, cta_final_line: str, forbidden_patterns: list[str]) -> None:
    codes: list[str] = []
    if str(atoms.get("cta_line") or "").strip() != str(cta_final_line or "").strip():
        codes.append("atoms_cta_mismatch")
    used_hooks = list(atoms.get("used_hook_ids") or [])
    if len(used_hooks) < 1:
        codes.append("atoms_missing_used_hook_ids")
    opener = str(atoms.get("opener_line") or "").lower()
    for pattern in forbidden_patterns:
        token = str(pattern or "").strip().lower()
        if token and token in opener:
            codes.append("atoms_forbidden_opener_pattern")
            break
    _codes_or_raise(codes)


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


def validate_email_draft(
    draft: dict[str, Any],
    *,
    brief: dict[str, Any],
    cta_final_line: str,
    sliders: dict[str, Any],
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

    length = str(sliders.get("length") or "medium")
    min_words, max_words = _length_band(length)
    wc = _word_count(body)
    if wc < min_words or wc > max_words:
        codes.append("word_count_out_of_band")

    tone_marker = float(sliders.get("framing", 0.5))
    if tone_marker >= personalization_threshold:
        opener = str(body.splitlines()[0] if body else "")
        if len(used_hook_ids) == 0:
            codes.append("personalization_missing_used_hook")
        if not _is_non_generic_opener(opener):
            codes.append("personalization_generic_opener")

    return codes


def normalize_qa_report(qa_report: dict[str, Any]) -> dict[str, Any]:
    report = dict(qa_report)
    issues = list(report.get("issues") or [])
    has_high = any(str(item.get("severity") or "").lower() == "high" for item in issues)
    pass_rewrite_needed = bool(report.get("pass_rewrite_needed")) or has_high
    report["pass_rewrite_needed"] = pass_rewrite_needed

    if pass_rewrite_needed and not report.get("rewrite_plan"):
        report["rewrite_plan"] = ["Tighten opener specificity.", "Remove fluff and keep one core ask."]
    return report
