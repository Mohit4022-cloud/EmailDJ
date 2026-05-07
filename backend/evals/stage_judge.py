from __future__ import annotations

from copy import deepcopy
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from app.engine.brief_honesty import (
    contaminated_research_fact_ids,
    fact_map_by_id,
    hook_is_prospect_as_proof,
    hook_support_posture,
    normalize_text_key,
)
from app.engine.schemas import JUDGE_RESULT_SCHEMA, RF_JUDGE_RESULT
from app.engine.stage_runner import _extract_message_text, _parse_message_content, _validate_schema
from app.engine.validators import (
    PROOF_GAP_TEXT,
    ValidationIssue,
    _contains_unsupported_proof_sentence as runtime_contains_unsupported_proof_sentence,
    build_cta_lock,
    build_proof_basis,
    canonicalize_proof_basis,
    canonical_hook_ids,
    normalize_cta_text,
    opener_contract,
    opener_is_simple,
    proof_basis_key,
    proof_is_vague,
    resolve_hook_ids,
    validate_angle_set,
    validate_fit_map,
    validate_messaging_brief,
)
from app.openai_client import ENFORCED_OPENAI_MODEL, OpenAIClient


STAGE_NAME_MAP = {
    "a": "CONTEXT_SYNTHESIS",
    "b": "FIT_REASONING",
    "b0": "ANGLE_PICKER",
    "c0": "ONE_LINER_COMPRESSOR",
    "c": "EMAIL_GENERATION",
    "d": "EMAIL_QA",
    "e": "EMAIL_REWRITE",
}

CRITERIA_BY_STAGE: dict[str, list[str]] = {
    "CONTEXT_SYNTHESIS": [
        "containment_clean",
        "assumptions_labeled",
        "hooks_grounded",
        "confidence_calibrated",
        "signal_strength_honest",
        "no_prospect_as_proof",
    ],
    "FIT_REASONING": [
        "hypotheses_grounded",
        "hook_ids_valid",
        "proof_specific",
        "why_now_honest",
        "ranking_justified",
    ],
    "ANGLE_PICKER": [
        "angles_distinct",
        "hook_ids_valid",
        "hypothesis_ids_valid",
        "why_you_why_now_earned",
        "risk_flags_inherited",
        "cta_bridge_natural",
    ],
    "ONE_LINER_COMPRESSOR": [
        "opener_specific",
        "opener_simple",
        "value_outcome_not_mechanism",
        "proof_not_circular",
        "cta_locked",
        "hook_ids_valid",
    ],
    "EMAIL_GENERATION": [
        "subject_specific",
        "subject_length",
        "no_atoms_violation",
        "value_visible",
        "proof_respected",
        "cta_exact",
        "no_banned_phrases",
        "no_double_cta",
    ],
    "EMAIL_QA": [
        "evidence_quoted",
        "fix_instructions_surgical",
        "severity_calibrated",
        "rewrite_plan_actionable",
    ],
    "EMAIL_REWRITE": [
        "high_issues_resolved",
        "no_new_content",
        "untouched_sentences_preserved",
        "cta_exact",
        "metadata_preserved",
    ],
}

PASS_THRESHOLD_BY_STAGE = {
    "CONTEXT_SYNTHESIS": 5,
    "FIT_REASONING": 4,
    "ANGLE_PICKER": 5,
    "ONE_LINER_COMPRESSOR": 5,
    "EMAIL_GENERATION": 6,
    "EMAIL_QA": 3,
    "EMAIL_REWRITE": 4,
}

HARD_FAIL_BY_STAGE = {
    "CONTEXT_SYNTHESIS": {"signal_strength_honest", "no_prospect_as_proof"},
    "FIT_REASONING": set(),
    "ANGLE_PICKER": set(),
    "ONE_LINER_COMPRESSOR": {"value_outcome_not_mechanism", "proof_not_circular"},
    "EMAIL_GENERATION": {"cta_exact", "no_banned_phrases"},
    "EMAIL_QA": {"fix_instructions_surgical"},
    "EMAIL_REWRITE": {"cta_exact"},
}

BANNED_PHRASES = [
    "touch base",
    "circle back",
    "synergy",
    "leverage",
    "game-changer",
    "revolutionary",
    "i hope this email finds you",
    "i hope this finds you",
    "i wanted to reach out",
    "just checking in",
    "quick question",
    "i came across your profile",
    "i know you're busy",
    "i'll keep this brief",
    "does that make sense",
    "let me know your thoughts",
    "hope to hear from you",
]

DEFAULT_DO_NOT_SAY = [
    "touch base",
    "circle back",
    "synergy",
    "leverage",
    "game-changer",
    "revolutionary",
    "I hope this email finds you",
    "I wanted to reach out",
    "just checking in",
]

_STAGE_A_CRITERIA_BY_VALIDATION_CODE = {
    "brief_missing_facts": ("containment_clean",),
    "fact_placeholder_text": ("containment_clean",),
    "fact_source_field_not_allowed": ("containment_clean",),
    "fact_contains_ungrounded_behavior_claim": ("containment_clean",),
    "fact_not_grounded_in_input": ("containment_clean",),
    "assumption_kind_invalid": ("assumptions_labeled",),
    "assumption_confidence_label_invalid": ("assumptions_labeled",),
    "assumption_high_confidence_no_grounding": ("assumptions_labeled", "confidence_calibrated"),
    "assumption_high_confidence_insufficient_facts": ("assumptions_labeled", "confidence_calibrated"),
    "assumption_placeholder_text": ("assumptions_labeled",),
    "brief_missing_hooks": ("hooks_grounded",),
    "hook_placeholder_text": ("hooks_grounded",),
    "hook_unknown_fact_id": ("hooks_grounded",),
    "hook_unknown_seller_fact_id": ("hooks_grounded",),
    "hook_seller_support_missing_fact_id": ("confidence_calibrated",),
    "hook_seller_fact_id_not_seller_side": ("no_prospect_as_proof",),
    "hook_missing_seller_proof_gap": ("confidence_calibrated",),
    "hook_prospect_as_proof": ("no_prospect_as_proof",),
    "hook_contaminated_research": ("hooks_grounded", "signal_strength_honest"),
    "hook_high_confidence_without_seller_proof": ("confidence_calibrated", "signal_strength_honest"),
    "hook_strong_evidence_without_seller_proof": ("signal_strength_honest",),
    "hook_unsupported_recency_or_initiative": ("hooks_grounded", "signal_strength_honest"),
    "hook_claim_too_strong_for_evidence": ("signal_strength_honest",),
    "brief_quality_overreach_risk_invalid": ("signal_strength_honest",),
    "brief_quality_signal_strength_mismatch": ("signal_strength_honest",),
}


def _as_list_of_strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _qa_issue_code(issue: dict[str, Any]) -> str:
    return str(issue.get("issue_code") or issue.get("type") or "").strip()


def _qa_issue_evidence_quotes(issue: dict[str, Any]) -> list[str]:
    evidence_quote = str(issue.get("evidence_quote") or "").strip()
    if evidence_quote:
        return [evidence_quote]
    return _as_list_of_strings(issue.get("evidence"))


def _rewrite_plan_actions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _override_scores(
    result: dict[str, Any],
    *,
    force_true: set[str] | None = None,
    force_false: set[str] | None = None,
    warning: str | None = None,
) -> dict[str, Any]:
    payload = dict(result)
    payload["scores"] = dict(result.get("scores") or {})
    for criterion in force_true or set():
        if criterion in payload["scores"]:
            payload["scores"][criterion] = 1
    for criterion in force_false or set():
        if criterion in payload["scores"]:
            payload["scores"][criterion] = 0
    warnings = _as_list_of_strings(payload.get("warnings"))
    if warning:
        _append_unique(warnings, warning)
    payload["warnings"] = warnings
    return _finalize_result(str(payload.get("stage") or ""), payload)


def _timing_signal_present(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    if re.search(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+20\d{2}\b", lowered):
        return True
    if re.search(r"\bq[1-4]\s+20\d{2}\b", lowered):
        return True
    if re.search(r"\b20\d{2}\b", lowered) and any(token in lowered for token in ("audit", "launch", "launched", "program", "initiative", "rollout", "expan")):
        return True
    return False


def _body_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", str(text or "")))


def _body_sentence_count(text: str) -> int:
    collapsed = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    if not collapsed:
        return 0
    return len([part for part in re.split(r"(?<=[.!?])\s+", collapsed) if part.strip()])


def _opener_clause_count(text: str) -> tuple[int, int]:
    collapsed = re.sub(r"\s+", " ", str(text or "").replace("\n", " ")).strip()
    opener = re.split(r"(?<=[.!?])\s+", collapsed)[0] if collapsed else ""
    return opener.count(","), len(re.findall(r"\b(which|that|because|so|and)\b", opener.lower()))


def _grounding_tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9']+", str(text or "").lower()) if len(token) >= 4}


def _proof_basis_for_artifact(
    *,
    proof_text: Any,
    proof_basis: dict[str, Any] | None,
    brief: dict[str, Any] | None,
    selected_hook_id: str = "",
    selected_fit_hypothesis_id: str = "",
) -> dict[str, Any]:
    provided = dict(proof_basis or {})
    if provided:
        return canonicalize_proof_basis(
            provided,
            messaging_brief=brief or {},
            selected_hook_id=selected_hook_id,
            selected_fit_hypothesis_id=selected_fit_hypothesis_id,
        )
    return canonicalize_proof_basis(
        build_proof_basis(
            proof_text,
            messaging_brief=brief or {},
            selected_hook_id=selected_hook_id,
            selected_fit_hypothesis_id=selected_fit_hypothesis_id,
        ),
        messaging_brief=brief or {},
        selected_hook_id=selected_hook_id,
        selected_fit_hypothesis_id=selected_fit_hypothesis_id,
    )


def _has_weak_proof_basis(proof_basis: dict[str, Any] | None, *, proof_gap: bool) -> bool:
    if proof_gap:
        return True
    kind = str(dict(proof_basis or {}).get("kind") or "").strip()
    return kind in {"none", "capability_statement", "assumption"}


def _angle_distinctness_signature(angle: dict[str, Any]) -> tuple[str, str, str, str]:
    proof_basis = dict(angle.get("proof_basis") or {})
    return (
        normalize_text_key(str(angle.get("primary_pain") or angle.get("pain") or "")),
        normalize_text_key(str(angle.get("primary_value_motion") or angle.get("value") or "")),
        normalize_text_key(str(angle.get("primary_proof_basis") or proof_basis_key(proof_basis))),
        normalize_text_key(str(angle.get("framing_type") or angle.get("angle_type") or "")),
    )


def _body_sentences_without_cta(body: str, *, cta_final_line: str) -> list[str]:
    locked_cta = normalize_cta_text(cta_final_line)
    narrative_lines = [
        line.strip()
        for line in str(body or "").splitlines()
        if line.strip() and normalize_cta_text(line) != locked_cta
    ]
    narrative = " ".join(narrative_lines).strip()
    if not narrative:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", narrative) if part.strip()]


def _matching_sentence_indexes(sentences: list[str], *candidates: Any) -> list[int]:
    normalized_sentences = [normalize_cta_text(sentence).lower() for sentence in sentences]
    indexes: list[int] = []
    for raw_candidate in candidates:
        candidate = normalize_cta_text(raw_candidate).lower()
        if not candidate:
            continue
        for idx, sentence in enumerate(normalized_sentences):
            if candidate in sentence or sentence in candidate:
                indexes.append(idx)
    return list(dict.fromkeys(indexes))


def _untouched_sentences_preserved(
    qa_report: dict[str, Any] | None,
    original_draft: dict[str, Any] | None,
    rewritten: dict[str, Any] | None,
    *,
    cta_final_line: str,
) -> bool:
    original_sentences = _body_sentences_without_cta(str((original_draft or {}).get("body") or ""), cta_final_line=cta_final_line)
    if not original_sentences:
        return True
    targeted: list[int] = []
    for issue in (qa_report or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        targeted.extend(
            _matching_sentence_indexes(
                original_sentences,
                issue.get("evidence_quote"),
                issue.get("offending_span_or_target_section"),
            )
        )
    for action in _rewrite_plan_actions((qa_report or {}).get("rewrite_plan")):
        targeted.extend(_matching_sentence_indexes(original_sentences, action.get("target")))
    targeted_indexes = set(targeted)
    rewritten_sentences = {
        normalize_cta_text(sentence)
        for sentence in _body_sentences_without_cta(str((rewritten or {}).get("body") or ""), cta_final_line=cta_final_line)
    }
    return all(
        normalize_cta_text(sentence) in rewritten_sentences
        for idx, sentence in enumerate(original_sentences)
        if idx not in targeted_indexes
    )


def _rewrite_high_issues_resolved(
    qa_report: dict[str, Any] | None,
    original_draft: dict[str, Any] | None,
    rewritten: dict[str, Any] | None,
    *,
    cta_final_line: str,
) -> bool:
    issues = [item for item in (qa_report or {}).get("issues") or [] if isinstance(item, dict)]
    high_issues = [item for item in issues if str(item.get("severity") or "").lower() == "high"]
    if not high_issues:
        return True

    original_body = str((original_draft or {}).get("body") or "")
    rewritten_body = str((rewritten or {}).get("body") or "")
    original_wc = _body_word_count(original_body)
    rewritten_wc = _body_word_count(rewritten_body)
    original_sentences = _body_sentence_count(original_body)
    rewritten_sentences = _body_sentence_count(rewritten_body)

    for issue in high_issues:
        code = _qa_issue_code(issue)
        if code == "word_count_out_of_band":
            action_text = " ".join(
                [
                    str(issue.get("fix_instruction") or ""),
                    str(issue.get("why_it_fails") or ""),
                    str(issue.get("expected_effect") or ""),
                ]
            ).lower()
            if "expand" in action_text:
                if rewritten_wc < original_wc + 8:
                    return False
            elif "compress" in action_text or "trim" in action_text:
                if rewritten_wc >= original_wc:
                    return False
            elif rewritten_wc == original_wc:
                return False
            continue
        if code == "too_many_sentences_for_preset":
            if rewritten_sentences >= original_sentences:
                return False
            continue
        if code == "opener_too_complex":
            original_commas, original_connectors = _opener_clause_count(original_body)
            rewritten_commas, rewritten_connectors = _opener_clause_count(rewritten_body)
            if rewritten_commas > original_commas or rewritten_connectors > original_connectors:
                return False
            continue
        if code == "cta_not_in_expected_form":
            if normalize_cta_text(_extract_last_nonempty_line(rewritten_body)) != normalize_cta_text(cta_final_line):
                return False
            continue
        return False
    return True


def _rewrite_no_new_content(
    rewritten: dict[str, Any] | None,
    *,
    proof_gap: bool,
    atoms: dict[str, Any] | None = None,
    cta_final_line: str = "",
) -> bool:
    body = str((rewritten or {}).get("body") or "")
    lowered = body.lower()
    if "[" in body or "]" in body:
        return False
    if _count_questions(body) != 1:
        return False
    if proof_gap and runtime_contains_unsupported_proof_sentence(
        body,
        cta_final_line=cta_final_line,
        message_atoms=atoms,
    ):
        return False
    return True


def _coerce_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    lowered = str(value or "").strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "1":
        return True
    if lowered == "0":
        return False
    return value


def _coerce_int(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return value


def _normalize_judge_payload_types(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["pass"] = _coerce_bool(normalized.get("pass"))
    normalized["hard_fail_triggered"] = _coerce_bool(normalized.get("hard_fail_triggered"))
    normalized["total"] = _coerce_int(normalized.get("total"))

    raw_scores = normalized.get("scores")
    if isinstance(raw_scores, dict):
        normalized["scores"] = {str(key): _coerce_int(value) for key, value in raw_scores.items()}

    return normalized


def _default_result(stage: str, *, failure: str | None = None) -> dict[str, Any]:
    criteria = CRITERIA_BY_STAGE[stage]
    failures = [failure] if failure else []
    return {
        "stage": stage,
        "scores": {criterion: 0 for criterion in criteria},
        "total": 0,
        "pass": False,
        "hard_fail_triggered": False,
        "hard_fail_criteria": [],
        "failures": failures,
        "warnings": [],
    }


def missing_artifact_result(stage: str, artifact_name: str) -> dict[str, Any]:
    return _default_result(stage, failure=f"artifact missing: {artifact_name}")


def _finalize_result(stage: str, payload: dict[str, Any]) -> dict[str, Any]:
    criteria = CRITERIA_BY_STAGE[stage]
    pass_threshold = PASS_THRESHOLD_BY_STAGE[stage]
    hard_fail_criteria = HARD_FAIL_BY_STAGE[stage]

    raw_scores = payload.get("scores") if isinstance(payload.get("scores"), dict) else {}
    scores = {criterion: int(raw_scores.get(criterion) == 1) for criterion in criteria}

    failures = _as_list_of_strings(payload.get("failures"))
    warnings = _as_list_of_strings(payload.get("warnings"))

    total = sum(scores.values())
    reported_total = payload.get("total")
    if isinstance(reported_total, int) and reported_total != total:
        _append_unique(warnings, f"normalized_total_from_{reported_total}_to_{total}")

    hard_failed = sorted([criterion for criterion in hard_fail_criteria if scores.get(criterion) == 0])
    hard_fail_triggered = bool(hard_failed)

    overall_pass = total >= pass_threshold and not hard_fail_triggered
    if bool(payload.get("pass")) != overall_pass:
        _append_unique(warnings, "normalized_pass_after_score_recompute")

    return {
        "stage": stage,
        "scores": scores,
        "total": total,
        "pass": overall_pass,
        "hard_fail_triggered": hard_fail_triggered,
        "hard_fail_criteria": hard_failed,
        "failures": failures,
        "warnings": warnings,
    }


def _apply_failures(result: dict[str, Any], *, forced_failures: list[tuple[str, str]]) -> dict[str, Any]:
    for criterion, failure_text in forced_failures:
        scores = result.get("scores") if isinstance(result.get("scores"), dict) else {}
        if criterion in scores:
            scores[criterion] = 0
            _append_unique(result["failures"], failure_text)
    return _finalize_result(str(result.get("stage") or ""), result)


def _stage_a_source_text(raw_inputs: dict[str, Any] | None) -> str:
    payload = raw_inputs if isinstance(raw_inputs, dict) else {}
    prospect = payload.get("prospect")
    if isinstance(prospect, dict):
        text = str(prospect.get("research_text") or "").strip()
        if text:
            return text
    return str(payload.get("research_text") or "").strip()


def _has_full_stage_a_source_payload(raw_inputs: dict[str, Any] | None) -> bool:
    payload = raw_inputs if isinstance(raw_inputs, dict) else {}
    return (
        isinstance(payload.get("prospect"), dict)
        and isinstance(payload.get("user_company"), dict)
        and isinstance(payload.get("cta"), dict)
    )


def _stage_a_validation_source_payload(raw_inputs: dict[str, Any] | None) -> dict[str, Any]:
    payload = raw_inputs if isinstance(raw_inputs, dict) else {}
    if _has_full_stage_a_source_payload(payload):
        return payload
    prospect = dict(payload.get("prospect") or {})
    user_company = dict(payload.get("user_company") or {})
    cta = dict(payload.get("cta") or {})
    company_context = dict(payload.get("company_context") or {})
    sender_profile_override = dict(payload.get("sender_profile_override") or {})
    return {
        "prospect": {
            "name": prospect.get("name"),
            "title": prospect.get("title"),
            "company": prospect.get("company"),
            "industry": prospect.get("industry"),
            "notes": prospect.get("notes") or payload.get("prospect_notes"),
            "research_text": prospect.get("research_text") or payload.get("research_text"),
        },
        "user_company": {
            "name": user_company.get("name") or company_context.get("company_name"),
            "product_summary": user_company.get("product_summary") or payload.get("offer_lock") or company_context.get("current_product"),
            "icp_description": user_company.get("icp_description") or sender_profile_override.get("structured_icp"),
            "differentiators": user_company.get("differentiators") or company_context.get("seller_offerings"),
            "proof_points": user_company.get("proof_points") or sender_profile_override.get("proof_points"),
            "do_not_say": user_company.get("do_not_say") or company_context.get("do_not_say") or payload.get("do_not_say") or list(DEFAULT_DO_NOT_SAY),
            "company_notes": user_company.get("company_notes") or company_context.get("company_notes"),
        },
        "cta": {
            "cta_type": cta.get("cta_type") or payload.get("cta_type") or company_context.get("cta_type"),
            "cta_final_line": cta.get("cta_final_line") or payload.get("cta_offer_lock") or company_context.get("cta_offer_lock"),
        },
    }


def _stage_a_failure_message(detail: dict[str, Any]) -> str:
    code = str(detail.get("code") or "").strip()
    hook_id = str(detail.get("hook_id") or "").strip()
    fact_id = str(detail.get("fact_id") or "").strip()
    offending_text = str(detail.get("offending_text") or "").strip()
    location = hook_id or fact_id or "brief"
    if offending_text:
        return f"{code}: {location}: {offending_text}"
    return f"{code}: {location}"


def _deterministic_stage_a_result(
    brief: dict[str, Any],
    *,
    raw_inputs: dict[str, Any] | None,
    artifact_views: dict[str, Any] | None,
) -> dict[str, Any]:
    stage = "CONTEXT_SYNTHESIS"
    payload = {
        "stage": stage,
        "scores": {criterion: 1 for criterion in CRITERIA_BY_STAGE[stage]},
        "total": len(CRITERIA_BY_STAGE[stage]),
        "pass": True,
        "hard_fail_triggered": False,
        "hard_fail_criteria": [],
        "failures": [],
        "warnings": [],
    }

    try:
        validate_messaging_brief(
            deepcopy(brief),
            source_text=_stage_a_source_text(raw_inputs),
            source_payload=_stage_a_validation_source_payload(raw_inputs),
        )
    except ValidationIssue as exc:
        criteria_to_fail: set[str] = set()
        for code in exc.codes:
            criteria_to_fail.update(_STAGE_A_CRITERIA_BY_VALIDATION_CODE.get(code, ("signal_strength_honest",)))
        for criterion in criteria_to_fail:
            payload["scores"][criterion] = 0
        if exc.details:
            for detail in exc.details:
                _append_unique(payload["failures"], _stage_a_failure_message(detail))
        else:
            for code in exc.codes:
                _append_unique(payload["failures"], code)

    facts = [item for item in (brief.get("facts_from_input") or []) if isinstance(item, dict)]
    hooks = [item for item in (brief.get("hooks") or []) if isinstance(item, dict)]
    fact_map = fact_map_by_id(facts)
    prospect_company = str(((raw_inputs or {}).get("prospect") or {}).get("company") or "").strip()
    contaminated_fact_ids = contaminated_research_fact_ids(facts, prospect_company=prospect_company or None)

    if any(hook_is_prospect_as_proof(hook, fact_map) for hook in hooks):
        payload["scores"]["no_prospect_as_proof"] = 0
        _append_unique(payload["failures"], "hook_prospect_as_proof: hook uses prospect context as seller proof")

    if any(
        hook_support_posture(hook, fact_map, contaminated_fact_ids=contaminated_fact_ids)["has_contamination_tainted_support"]
        for hook in hooks
    ):
        payload["scores"]["hooks_grounded"] = 0
        payload["scores"]["signal_strength_honest"] = 0
        _append_unique(payload["failures"], "hook_contaminated_research: hook uses contaminated research about another company")

    raw_hygiene_issue_count = int(dict((artifact_views or {}).get("raw_artifact_quality") or {}).get("issue_count") or 0)
    if raw_hygiene_issue_count:
        _append_unique(payload["warnings"], f"raw_hygiene_issues_present:{raw_hygiene_issue_count}")

    finalized = _finalize_result(stage, payload)
    if payload["failures"]:
        finalized["pass"] = False
    return finalized


def _write_judge_trace(
    *,
    run_id: str | None,
    payload_id: str | None,
    stage: str,
    request_artifacts: dict[str, Any],
    messages: list[dict[str, str]],
    response_payload: dict[str, Any] | None,
    response_raw: dict[str, Any] | None,
    result: dict[str, Any],
    error: str | None,
    elapsed_ms: int,
) -> None:
    if not run_id:
        return
    root = _BACKEND_ROOT / "debug_traces" / "evals" / str(run_id)
    root.mkdir(parents=True, exist_ok=True)
    safe_payload_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(payload_id or "unknown_payload"))
    filename = f"{safe_payload_id}_{stage}.json"
    payload = {
        "run_id": run_id,
        "payload_id": payload_id,
        "stage": stage,
        "elapsed_ms": elapsed_ms,
        "request_artifacts": request_artifacts,
        "messages": messages,
        "response_payload": response_payload,
        "response_raw": response_raw,
        "result": result,
        "error": error,
    }
    (root / filename).write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


async def _call_judge_llm(*, openai: OpenAIClient, messages: list[dict[str, str]], timeout_seconds: float = 45.0) -> tuple[dict[str, Any], dict[str, Any]]:
    response = await openai.chat_completion(
        model=ENFORCED_OPENAI_MODEL,
        messages=messages,
        reasoning_effort="minimal",
        max_completion_tokens=1000,
        timeout_seconds=timeout_seconds,
    )
    text = _extract_message_text(dict(response.get("message") or {}))
    payload = _normalize_judge_payload_types(_parse_message_content(text))
    _validate_schema(payload, {"json_schema": {"schema": JUDGE_RESULT_SCHEMA}})
    return payload, response


def _judge_system_prompt() -> str:
    return (
        "You are an automated QA evaluator for a cold email generation pipeline. "
        "You score outputs against explicit rubrics. You output only JSON. "
        "You never explain scores in prose outside failures[] and warnings[]. "
        "You are strict: partial credit does not exist. A criterion either passes (1) or fails (0)."
    )


def _judge_user_prompt(
    *,
    stage: str,
    criteria: list[str],
    rubric_text: str,
    artifacts: dict[str, Any],
    examples_text: str | None = None,
) -> str:
    schema_preview = {
        "stage": stage,
        "scores": {criterion: "0|1" for criterion in criteria},
        "total": len(criteria),
        "pass": "boolean",
        "hard_fail_triggered": "boolean",
        "hard_fail_criteria": ["criterion_name"],
        "failures": ["string"],
        "warnings": ["string"],
    }
    parts = [
        f"Stage: {stage}",
        "Rubric (strict pass/fail per criterion):",
        rubric_text,
        "Artifacts JSON:",
        json.dumps(artifacts, ensure_ascii=True, indent=2),
    ]
    if examples_text:
        parts.extend(["Reasoning examples (pass/fail bar):", examples_text])
    parts.extend(
        [
            "Output schema contract:",
            json.dumps(schema_preview, ensure_ascii=True, indent=2),
            "Use integers for scores and total.",
            "Return only valid JSON.",
        ]
    )
    return "\n\n".join(parts)

def _check_bracket_placeholder(text: str) -> bool:
    return bool(re.search(r"\[[^\]]+\]", str(text or "")))


def _check_outcome_like(text: str) -> bool:
    lowered = str(text or "").lower()
    has_metric = bool(re.search(r"\b\d+[%xk]?\b", lowered))
    has_time = any(token in lowered for token in ("week", "month", "quarter", "day", "within", "faster"))
    outcome_words = (
        "reduce",
        "reduced",
        "improve",
        "improved",
        "increase",
        "increased",
        "lift",
        "lifted",
        "fewer",
        "less",
        "more",
        "higher",
        "lower",
        "cut",
        "protect",
        "stabilize",
        "scale",
        "scaled",
        "keep",
        "keeps",
        "maintain",
        "maintains",
        "standardize",
        "standardized",
        "tighten",
        "tightened",
    )
    has_outcome_verb = any(word in lowered for word in outcome_words)
    mechanism_words = (
        "scoring",
        "tracking",
        "platform",
        "tool",
        "system",
        "workflow",
        "qa",
        "process",
        "cadence",
    )
    has_mechanism = any(word in lowered for word in mechanism_words)
    concrete_outcome_words = (
        "reliability",
        "accuracy",
        "consistency",
        "coverage",
        "conversion",
        "variance",
        "lag",
        "delay",
        "leakage",
        "throughput",
        "quality",
        "handoff",
        "forecast",
        "pipeline",
    )
    gain_fallback = bool(re.search(r"\bgain(?:s|ed)?\b", lowered)) and any(
        word in lowered for word in concrete_outcome_words
    )
    if has_mechanism and not (has_metric or has_time or has_outcome_verb):
        return gain_fallback
    return has_metric or has_time or has_outcome_verb or gain_fallback


def _proof_looks_circular(proof_line: str, brief: dict[str, Any], angle: dict[str, Any] | None = None) -> bool:
    proof = str(proof_line or "").strip().lower()
    if not proof:
        return False

    prospect_company = ""
    facts = brief.get("facts_from_input") if isinstance(brief.get("facts_from_input"), list) else []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        source = str(fact.get("source_field") or "").lower()
        text = str(fact.get("text") or "").strip().lower()
        if source in {"prospect_context", "research", "research_text"} and text and text in proof:
            return True
        if "company:" in text:
            prospect_company = text.split("company:", 1)[-1].strip()

    if prospect_company and prospect_company in proof:
        return True

    if angle and isinstance(angle, dict):
        angle_proof = str(angle.get("proof") or "").strip().lower()
        if angle_proof and angle_proof == proof:
            return True

    return False


def _extract_last_nonempty_line(body: str) -> str:
    lines = [line.strip() for line in str(body or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _count_questions(body: str) -> int:
    return str(body or "").count("?")


def _non_actionable_fix_instruction(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return True
    vague_only = [
        "make it more specific",
        "improve the opener",
        "be more concrete",
        "tighten this",
        "make it better",
    ]
    if lowered in vague_only:
        return True
    action_markers = ("replace", "remove", "delete", "move", "trim", "shorten", "keep", "rewrite")
    target_markers = ("quote", "target", "line", "sentence", "subject", "opener", "body", "span", "cta")
    if ("make it" in lowered or "improve" in lowered) and not any(token in lowered for token in target_markers):
        return True
    if not any(token in lowered for token in action_markers):
        return True
    if not any(token in lowered for token in target_markers):
        return True
    return False


def _rewrite_action_is_actionable(action: dict[str, Any], issue_codes: set[str]) -> bool:
    required_fields = ("issue_code", "target", "action", "replacement_guidance", "preserve", "expected_effect")
    if any(not str(action.get(field) or "").strip() for field in required_fields):
        return False
    issue_code = str(action.get("issue_code") or "").strip()
    if issue_codes and issue_code not in issue_codes:
        return False
    if _non_actionable_fix_instruction(str(action.get("action") or "")):
        return False
    if _non_actionable_fix_instruction(str(action.get("replacement_guidance") or "")):
        return False
    return True


async def _run_stage_judge(
    *,
    stage: str,
    artifacts: dict[str, Any],
    rubric_text: str,
    examples_text: str | None,
    openai: OpenAIClient,
    run_id: str | None,
    payload_id: str | None,
) -> dict[str, Any]:
    criteria = CRITERIA_BY_STAGE[stage]
    missing_keys = [key for key, value in artifacts.items() if value is None and key == "artifact"]
    if missing_keys:
        return missing_artifact_result(stage, missing_keys[0])

    messages = [
        {"role": "system", "content": _judge_system_prompt()},
        {
            "role": "user",
            "content": _judge_user_prompt(
                stage=stage,
                criteria=criteria,
                rubric_text=rubric_text,
                artifacts=artifacts,
                examples_text=examples_text,
            ),
        },
    ]

    started = time.perf_counter()
    response_payload: dict[str, Any] | None = None
    response_raw: dict[str, Any] | None = None
    error_text: str | None = None
    try:
        response_payload, response_raw = await _call_judge_llm(openai=openai, messages=messages)
        response_payload["stage"] = stage
        result = _finalize_result(stage, response_payload)
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        result = _default_result(stage, failure=f"judge_call_failed:{error_text}")

    elapsed_ms = int(round((time.perf_counter() - started) * 1000))
    _write_judge_trace(
        run_id=run_id,
        payload_id=payload_id,
        stage=stage,
        request_artifacts=artifacts,
        messages=messages,
        response_payload=response_payload,
        response_raw=response_raw,
        result=result,
        error=error_text,
        elapsed_ms=elapsed_ms,
    )
    return result


async def judge_messaging_brief(
    brief: dict[str, Any] | None,
    raw_inputs: dict[str, Any] | None,
    artifact_views: dict[str, Any] | None = None,
    *,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "CONTEXT_SYNTHESIS"
    semantic_brief = dict((artifact_views or {}).get("sanitized_stage_a_artifact") or brief or {})
    if not semantic_brief:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) containment_clean: facts must be traceable to explicit source fields.
2) assumptions_labeled: uncertain language belongs in assumptions, not facts.
3) hooks_grounded: every hook references valid fact ids.
4) confidence_calibrated: high-confidence reasoning requires multiple supporting facts and honest labels.
5) signal_strength_honest: signal strength must match evidence origin and hook evidence_strength, not just volume.
6) no_prospect_as_proof: seller support/proof may not rely on prospect-only context.
""".strip()

    llm_result = await _run_stage_judge(
        stage=stage,
        artifacts={
            "artifact": semantic_brief,
            "raw_inputs": raw_inputs or {},
            "raw_hygiene": {
                "raw_hygiene_issues": list((artifact_views or {}).get("raw_hygiene_issues") or []),
                "raw_artifact_quality": dict((artifact_views or {}).get("raw_artifact_quality") or {}),
            },
            "sanitation_report": dict((artifact_views or {}).get("sanitation_report") or {}),
        },
        rubric_text=rubric,
        examples_text=None,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )
    finalized = _deterministic_stage_a_result(
        semantic_brief,
        raw_inputs=raw_inputs,
        artifact_views=artifact_views,
    )
    for warning in _as_list_of_strings(llm_result.get("warnings")):
        if warning.startswith("raw_hygiene_issues_present:"):
            continue
        _append_unique(finalized["warnings"], warning)
    return finalized


async def judge_fit_map(
    fit_map: dict[str, Any] | None,
    brief: dict[str, Any] | None,
    *,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "FIT_REASONING"
    if not fit_map:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) hypotheses_grounded: supporting_fact_ids map to brief facts.
2) hook_ids_valid: selected_hook_id exists in brief hooks.
3) proof_specific: proof is specific outcome/proof or explicit no-proof fallback.
4) why_now_honest: urgency statements are source-backed or explicitly evergreen.
5) ranking_justified: top-ranked hypothesis aligns with highest confidence unless override explained.
""".strip()

    result = await _run_stage_judge(
        stage=stage,
        artifacts={"artifact": fit_map, "brief": brief or {}},
        rubric_text=rubric,
        examples_text=None,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )

    forced: list[tuple[str, str]] = []
    objective_true: set[str] = set()
    hypotheses = [item for item in (fit_map.get("hypotheses") or []) if isinstance(item, dict)]
    fact_ids = {
        str(item.get("fact_id") or "").strip()
        for item in (brief or {}).get("facts_from_input") or []
        if isinstance(item, dict) and str(item.get("fact_id") or "").strip()
    }

    try:
        validate_fit_map(deepcopy(fit_map), deepcopy(brief or {}))
    except ValidationIssue as exc:
        for code in exc.codes:
            if code in {"fit_unknown_hook_id"}:
                forced.append(("hook_ids_valid", code))
            elif code in {"fit_missing_supporting_facts", "fit_unknown_supporting_fact_id"}:
                forced.append(("hypotheses_grounded", code))
            elif code in {
                "fit_missing_proof_basis",
                "fit_proof_basis_missing_source_fact",
                "fit_proof_basis_unknown_fact_id",
                "fit_proof_gap_text_mismatch",
                "fit_proof_not_specific",
            }:
                forced.append(("proof_specific", code))

    hooks_valid = True
    hypotheses_grounded = True
    proof_specific = True
    ranked_hypotheses = sorted(
        hypotheses,
        key=lambda item: (int(item.get("rank") or 999), -float(item.get("confidence") or 0.0)),
    )
    if ranked_hypotheses:
        top = ranked_hypotheses[0]
        top_confidence = float(top.get("confidence") or 0.0)
        max_confidence = max(float(item.get("confidence") or 0.0) for item in ranked_hypotheses)
        if top_confidence >= max_confidence:
            objective_true.add("ranking_justified")

    for hyp in hypotheses:
        selected_hook_id = str(hyp.get("selected_hook_id") or "").strip()
        fit_hypothesis_id = str(hyp.get("fit_hypothesis_id") or "").strip()
        resolved_hook_ids, _ = resolve_hook_ids(
            [selected_hook_id],
            messaging_brief=brief or {},
            selected_hook_id=selected_hook_id,
        )
        if not resolved_hook_ids:
            hooks_valid = False

        supporting_fact_ids = [
            str(item or "").strip()
            for item in (hyp.get("supporting_fact_ids") or [])
            if str(item or "").strip()
        ]
        if not supporting_fact_ids or any(item not in fact_ids for item in supporting_fact_ids):
            hypotheses_grounded = False

        proof_text = str(hyp.get("proof") or "").strip()
        proof_basis = _proof_basis_for_artifact(
            proof_text=proof_text,
            proof_basis=dict(hyp.get("proof_basis") or {}),
            brief=brief,
            selected_hook_id=selected_hook_id,
            selected_fit_hypothesis_id=fit_hypothesis_id,
        )
        basis_kind = str(proof_basis.get("kind") or "").strip()
        basis_fact_ids = [
            str(item or "").strip()
            for item in (proof_basis.get("source_fact_ids") or [])
            if str(item or "").strip()
        ]
        derived_basis = build_proof_basis(
            proof_text,
            messaging_brief=brief or {},
            selected_hook_id=selected_hook_id,
            selected_fit_hypothesis_id=fit_hypothesis_id,
        )
        if basis_kind == "none":
            if proof_text != PROOF_GAP_TEXT:
                proof_specific = False
        else:
            if proof_is_vague(proof_text):
                proof_specific = False
            if basis_kind in {"hard_proof", "soft_signal"} and (
                not basis_fact_ids
                or any(item not in fact_ids for item in basis_fact_ids)
                or str(derived_basis.get("kind") or "").strip() not in {"hard_proof", "soft_signal"}
            ):
                proof_specific = False

    if hooks_valid:
        objective_true.add("hook_ids_valid")
    else:
        forced.append(("hook_ids_valid", "selected_hook_id does not resolve to canonical brief hooks"))

    if hypotheses_grounded:
        objective_true.add("hypotheses_grounded")
    else:
        forced.append(("hypotheses_grounded", "supporting_fact_ids do not map to brief facts"))

    if proof_specific:
        objective_true.add("proof_specific")
    else:
        forced.append(("proof_specific", "proof basis is vague, mismatched, or ungrounded"))

    result = _apply_failures(result, forced_failures=forced)
    if objective_true:
        result = _override_scores(
            result,
            force_true=objective_true,
            warning="deterministic_override:fit_contract_checks",
        )
    return result


async def judge_angle_set(
    angle_set: dict[str, Any] | None,
    brief: dict[str, Any] | None,
    fit_map: dict[str, Any] | None,
    *,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "ANGLE_PICKER"
    if not angle_set:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) angles_distinct: no duplicate angle_type or duplicate selected_hook_id.
2) hook_ids_valid: all selected_hook_id values exist in brief hooks.
3) hypothesis_ids_valid: all selected_fit_hypothesis_id values exist in fit map.
4) why_you_why_now_earned: why_you_why_now only when timing signal is grounded.
5) risk_flags_inherited: inherited hypothesis risk flags are preserved.
6) cta_bridge_natural: CTA suggestion is a <=160 char question.
""".strip()

    result = await _run_stage_judge(
        stage=stage,
        artifacts={"artifact": angle_set, "brief": brief or {}, "fit_map": fit_map or {}},
        rubric_text=rubric,
        examples_text=None,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )

    forced: list[tuple[str, str]] = []
    objective_true: set[str] = set()
    seen_signatures: set[tuple[str, str, str, str]] = set()
    seen_angle_types: set[str] = set()
    seen_hook_ids: set[str] = set()
    fact_map = fact_map_by_id((brief or {}).get("facts_from_input") or [])
    canonical_brief_hook_ids = canonical_hook_ids(brief or {})
    hypothesis_map = {
        str(item.get("fit_hypothesis_id") or ""): item
        for item in (fit_map or {}).get("hypotheses") or []
        if isinstance(item, dict)
    }
    why_now_grounded = False
    hooks_valid = True
    hypothesis_ids_valid = True
    risk_flags_inherited = True
    cta_bridge_natural = True
    if len(list(angle_set.get("angles") or [])) < 3:
        forced.append(("angles_distinct", "angle_set must contain at least three angles"))

    try:
        validate_angle_set(deepcopy(angle_set), deepcopy(brief or {}), deepcopy(fit_map or {}))
    except ValidationIssue as exc:
        for code in exc.codes:
            if code in {"angle_set_too_small", "angle_duplicate_distinctness_signature"}:
                forced.append(("angles_distinct", code))
            elif code in {"angle_unknown_hook_id"}:
                forced.append(("hook_ids_valid", code))
            elif code in {"angle_unknown_fit_hypothesis_id"}:
                forced.append(("hypothesis_ids_valid", code))

    for angle in angle_set.get("angles") or []:
        if not isinstance(angle, dict):
            continue
        angle_type = str(angle.get("angle_type") or "")
        hook_id = str(angle.get("selected_hook_id") or "")
        resolved_hook_ids, _ = resolve_hook_ids(
            [hook_id],
            messaging_brief=brief or {},
            selected_hook_id=hook_id,
        )
        if not resolved_hook_ids:
            hooks_valid = False
        signature = _angle_distinctness_signature(angle)
        if signature in seen_signatures:
            forced.append(("angles_distinct", f"duplicate distinctness signature for '{str(angle.get('angle_id') or '')}'"))
        else:
            seen_signatures.add(signature)
        if angle_type and angle_type in seen_angle_types:
            forced.append(("angles_distinct", f"duplicate angle_type for '{str(angle.get('angle_id') or '')}'"))
        elif angle_type:
            seen_angle_types.add(angle_type)
        if len(canonical_brief_hook_ids) > 1:
            if hook_id and hook_id in seen_hook_ids:
                forced.append(("angles_distinct", f"duplicate selected_hook_id for '{str(angle.get('angle_id') or '')}'"))
            elif hook_id:
                seen_hook_ids.add(hook_id)
        hypothesis = hypothesis_map.get(str(angle.get("selected_fit_hypothesis_id") or ""), {})
        if not hypothesis:
            hypothesis_ids_valid = False
        else:
            inherited = {
                str(item or "").strip()
                for item in (hypothesis.get("risk_flags") or [])
                if str(item or "").strip()
            }
            current = {
                str(item or "").strip()
                for item in (angle.get("risk_flags") or [])
                if str(item or "").strip()
            }
            if not inherited.issubset(current):
                risk_flags_inherited = False
        cta = str(angle.get("cta_question_suggestion") or "").strip()
        if cta and (not cta.endswith("?") or len(cta) > 160):
            forced.append(("cta_bridge_natural", "cta_question_suggestion must be <=160 chars and end with ?"))
            cta_bridge_natural = False
        if angle_type == "why_you_why_now":
            referenced_text: list[str] = [
                str(angle.get("pain") or ""),
                str(angle.get("impact") or ""),
                str(angle.get("proof") or ""),
            ]
            hook = next(
                (
                    item
                    for item in (brief or {}).get("hooks") or []
                    if isinstance(item, dict) and str(item.get("hook_id") or "") == hook_id
                ),
                {},
            )
            for fact_id in list(hook.get("supported_by_fact_ids") or []):
                fact = fact_map.get(str(fact_id) or "")
                if isinstance(fact, dict):
                    referenced_text.append(str(fact.get("text") or ""))
            hypothesis = hypothesis_map.get(str(angle.get("selected_fit_hypothesis_id") or ""), {})
            for fact_id in list(hypothesis.get("supporting_fact_ids") or []):
                fact = fact_map.get(str(fact_id) or "")
                if isinstance(fact, dict):
                    referenced_text.append(str(fact.get("text") or ""))
            if any(_timing_signal_present(text) for text in referenced_text):
                why_now_grounded = True

    result = _apply_failures(result, forced_failures=forced)
    if hooks_valid:
        objective_true.add("hook_ids_valid")
    if hypothesis_ids_valid:
        objective_true.add("hypothesis_ids_valid")
    if risk_flags_inherited:
        objective_true.add("risk_flags_inherited")
    if cta_bridge_natural:
        objective_true.add("cta_bridge_natural")
    if len(seen_signatures) == len([item for item in (angle_set.get("angles") or []) if isinstance(item, dict)]) and len(seen_signatures) >= 3:
        objective_true.add("angles_distinct")
    if why_now_grounded:
        objective_true.add("why_you_why_now_earned")
    if objective_true:
        result = _override_scores(
            result,
            force_true=objective_true,
            warning="deterministic_override:angle_contract_checks",
        )
    return result


async def judge_message_atoms(
    atoms: dict[str, Any] | None,
    brief: dict[str, Any] | None,
    angle: dict[str, Any] | None,
    *,
    locked_cta: str,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "ONE_LINER_COMPRESSOR"
    if not atoms:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) opener_specific: opener must be specific to this prospect/company context.
2) opener_simple: opener has <=1 comma and avoids stacked conjunctions.
3) value_outcome_not_mechanism: value line states outcome, not mechanism or imperative.
4) proof_not_circular: proof cannot restate prospect facts; empty proof is allowed.
5) cta_locked: cta_atom and required_cta_line must match locked CTA character-for-character.
6) hook_ids_valid: used_hook_ids are valid brief hook ids.
""".strip()

    examples = """
PASS value_outcome_not_mechanism: "RevOps teams cut handoff delays by 18% in one quarter."
FAIL value_outcome_not_mechanism: "Use our workflow QA platform for scoring and tracking."
PASS proof_not_circular: "A fintech customer lifted meetings 22% after QA rollout."
FAIL proof_not_circular: proof repeats the prospect's own research facts as seller proof.
""".strip()

    result = await _run_stage_judge(
        stage=stage,
        artifacts={"artifact": atoms, "brief": brief or {}, "angle": angle or {}, "locked_cta": locked_cta},
        rubric_text=rubric,
        examples_text=examples,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )

    forced: list[tuple[str, str]] = []
    objective_true: set[str] = set()
    selected_hook_id = str((angle or {}).get("selected_hook_id") or "")
    cta_lock = build_cta_lock(locked_cta)
    opener_line = str(atoms.get("opener_line") or atoms.get("opener_atom") or "")
    value_line = str(atoms.get("value_atom") or "")
    proof_line = str(atoms.get("proof_atom") or "")
    cta_line = str(atoms.get("cta_atom") or "")
    required_cta_line = str(atoms.get("required_cta_line") or "")
    proof_basis = _proof_basis_for_artifact(
        proof_text=proof_line,
        proof_basis=dict(atoms.get("proof_basis") or {}),
        brief=brief,
        selected_hook_id=selected_hook_id,
        selected_fit_hypothesis_id=str((angle or {}).get("selected_fit_hypothesis_id") or ""),
    )
    atoms_cta_lock = dict(atoms.get("cta_lock") or {})

    if _check_bracket_placeholder(opener_line) or _check_bracket_placeholder(value_line):
        forced.append(("value_outcome_not_mechanism", "placeholder bracket token leaked in atoms"))

    if not _check_outcome_like(value_line):
        forced.append(("value_outcome_not_mechanism", "value_line describes mechanism without concrete outcome"))

    if proof_line and _proof_looks_circular(proof_line, brief or {}, angle=angle or {}):
        forced.append(("proof_not_circular", "proof_line appears circular or prospect-derived"))

    if (
        normalize_cta_text(cta_line) != cta_lock["final_line"]
        or normalize_cta_text(required_cta_line) != cta_lock["final_line"]
        or normalize_cta_text(atoms_cta_lock.get("final_line") or "") != cta_lock["final_line"]
    ):
        forced.append(("cta_locked", "atoms CTA fields do not match locked CTA"))
    else:
        objective_true.add("cta_locked")

    if not opener_is_simple(opener_line, contract=dict(atoms.get("opener_contract") or opener_contract())):
        forced.append(("opener_simple", "opener contains too many clauses"))
    else:
        objective_true.add("opener_simple")

    used_hook_ids = [str(item or "") for item in atoms.get("used_hook_ids") or []]
    resolved_hook_ids, repair_actions = resolve_hook_ids(
        used_hook_ids,
        messaging_brief=brief or {},
        selected_hook_id=selected_hook_id,
    )
    canonical_hooks = set(canonical_hook_ids(brief or {}))
    canonical_hook_ids_in_atoms = [str(item or "").strip() for item in (atoms.get("canonical_hook_ids") or []) if str(item or "").strip()]
    normalized_used_hook_ids = [str(item or "").strip() for item in used_hook_ids if str(item or "").strip()]
    if (
        not resolved_hook_ids
        or normalized_used_hook_ids != resolved_hook_ids
        or any(item not in canonical_hooks for item in canonical_hook_ids_in_atoms)
        or canonical_hook_ids_in_atoms != canonical_hook_ids(brief or {})
        or (selected_hook_id and selected_hook_id not in resolved_hook_ids)
    ):
        forced.append(("hook_ids_valid", "used_hook_ids do not resolve to canonical brief hooks"))
    if len(set(used_hook_ids)) != len(used_hook_ids):
        forced.append(("hook_ids_valid", "used_hook_ids contains duplicate hook ids"))
    elif not any(criterion == "hook_ids_valid" for criterion, _ in forced) and resolved_hook_ids and set(canonical_hook_ids_in_atoms or resolved_hook_ids).issubset(canonical_hooks):
        objective_true.add("hook_ids_valid")

    if proof_line and _check_outcome_like(proof_line):
        if str(proof_basis.get("kind") or "").strip() in {"none", "capability_statement", "assumption"}:
            forced.append(("proof_not_circular", "proof line overclaims beyond grounded proof basis"))
    elif not proof_line:
        objective_true.add("proof_not_circular")

    result = _apply_failures(result, forced_failures=forced)
    if objective_true:
        result = _override_scores(
            result,
            force_true=objective_true,
            warning="deterministic_override:atoms_contract_checks",
        )
    return result


async def judge_email_draft(
    draft: dict[str, Any] | None,
    atoms: dict[str, Any] | None,
    brief: dict[str, Any] | None,
    *,
    cta_final_line: str,
    proof_gap: bool,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "EMAIL_GENERATION"
    if not draft:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) subject_specific: specific and non-generic subject.
2) subject_length: <=70 chars.
3) no_atoms_violation: no extra claims beyond atoms.
4) value_visible: value atom is a distinct sentence.
5) proof_respected: proof presence/absence follows proof_gap.
6) cta_exact: final body line exactly equals locked CTA.
7) no_banned_phrases: banned phrase list never appears.
8) no_double_cta: exactly one question and it is the locked CTA.
""".strip()

    examples = """
PASS cta_exact: body last line equals locked CTA exactly.
FAIL cta_exact: CTA paraphrased or extra punctuation.
PASS no_banned_phrases: no outreach cliches.
FAIL no_banned_phrases: includes "touch base" or "quick question".
""".strip()

    result = await _run_stage_judge(
        stage=stage,
        artifacts={
            "artifact": draft,
            "atoms": atoms or {},
            "brief": brief or {},
            "cta_final_line": cta_final_line,
            "proof_gap": bool(proof_gap),
        },
        rubric_text=rubric,
        examples_text=examples,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )

    forced: list[tuple[str, str]] = []
    objective_true: set[str] = set()
    subject = str(draft.get("subject") or "").strip()
    body = str(draft.get("body") or "")
    cta_lock = build_cta_lock(cta_final_line)
    last_line = normalize_cta_text(_extract_last_nonempty_line(body))
    proof_basis = _proof_basis_for_artifact(
        proof_text=str((atoms or {}).get("proof_atom") or ""),
        proof_basis=dict((atoms or {}).get("proof_basis") or {}),
        brief=brief,
        selected_hook_id=str(((atoms or {}).get("used_hook_ids") or [""])[0] or ""),
        selected_fit_hypothesis_id=str((atoms or {}).get("selected_angle_id") or ""),
    )

    if len(subject) > 70:
        forced.append(("subject_length", "subject exceeds 70 characters"))

    if last_line != cta_lock["final_line"]:
        forced.append(("cta_exact", "final body line does not exactly match locked CTA"))
    else:
        objective_true.add("cta_exact")

    lowered_text = f"{subject}\n{body}".lower()
    for banned in BANNED_PHRASES:
        if banned in lowered_text:
            forced.append(("no_banned_phrases", f"contains banned phrase '{banned}'"))
            break
    else:
        objective_true.add("no_banned_phrases")

    cta_line_count = sum(1 for line in body.splitlines() if normalize_cta_text(line) == cta_lock["final_line"])
    if _count_questions(body) != 1 or cta_line_count != 1:
        forced.append(("no_double_cta", "body must contain exactly one question mark"))
    else:
        objective_true.add("no_double_cta")

    if _has_weak_proof_basis(proof_basis, proof_gap=proof_gap) and runtime_contains_unsupported_proof_sentence(
        body,
        cta_final_line=cta_lock["final_line"],
        message_atoms=atoms,
    ):
        forced.append(("proof_respected", "proof sentence appears despite proof_gap"))
    else:
        proof_atom = str((atoms or {}).get("proof_atom") or "").strip()
        if proof_atom and not _has_weak_proof_basis(proof_basis, proof_gap=proof_gap):
            proof_tokens = _grounding_tokens(proof_atom)
            body_sentences = _body_sentences_without_cta(body, cta_final_line=cta_lock["final_line"])
            if not any(len(_grounding_tokens(sentence) & proof_tokens) >= 2 for sentence in body_sentences):
                forced.append(("proof_respected", "grounded proof atom is not represented in the body"))
            else:
                objective_true.add("proof_respected")
        else:
            objective_true.add("proof_respected")

    result = _apply_failures(result, forced_failures=forced)
    if objective_true:
        result = _override_scores(
            result,
            force_true=objective_true,
            warning="deterministic_override:generation_contract_checks",
        )
    return result


async def judge_qa_report(
    qa_report: dict[str, Any] | None,
    draft: dict[str, Any] | None,
    *,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "EMAIL_QA"
    if not qa_report:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) evidence_quoted: each issue includes draft-quoted evidence.
2) fix_instructions_surgical: each fix_instruction says what to change and where to source replacement.
3) severity_calibrated: structural failures are high; stylistic preferences are not high.
4) rewrite_plan_actionable: rewrite plan is executable if rewrite is required.
""".strip()

    result = await _run_stage_judge(
        stage=stage,
        artifacts={"artifact": qa_report, "draft": draft or {}},
        rubric_text=rubric,
        examples_text=None,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )

    forced: list[tuple[str, str]] = []
    issues = qa_report.get("issues") if isinstance(qa_report.get("issues"), list) else []
    draft_blob = f"{(draft or {}).get('subject', '')}\n{(draft or {}).get('body', '')}".strip()
    issue_codes = {_qa_issue_code(issue) for issue in issues if isinstance(issue, dict) and _qa_issue_code(issue)}

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        evidence = _qa_issue_evidence_quotes(issue)
        if not evidence or not all(snippet in draft_blob for snippet in evidence):
            forced.append(("evidence_quoted", "issue evidence is not directly quoted from draft"))
        fix_instruction = str(issue.get("fix_instruction") or "")
        target = str(issue.get("offending_span_or_target_section") or "").strip()
        if not _qa_issue_code(issue) or not target or _non_actionable_fix_instruction(fix_instruction):
            forced.append(("fix_instructions_surgical", "fix_instruction is directional but not surgical"))

    rewrite_actions = _rewrite_plan_actions(qa_report.get("rewrite_plan"))
    if bool(qa_report.get("pass_rewrite_needed")):
        if not rewrite_actions:
            forced.append(("rewrite_plan_actionable", "pass_rewrite_needed true but rewrite_plan is empty"))
        elif any(not _rewrite_action_is_actionable(action, issue_codes) for action in rewrite_actions):
            forced.append(("rewrite_plan_actionable", "rewrite_plan action is missing issue mapping or localized target"))

    result = _apply_failures(result, forced_failures=forced)
    objective_true: set[str] = set()
    if issues and all(_qa_issue_evidence_quotes(issue) for issue in issues):
        objective_true.add("evidence_quoted")
    if issues and all(
        str(issue.get("offending_span_or_target_section") or "").strip()
        and len(str(issue.get("fix_instruction") or "").strip()) >= 20
        for issue in issues
    ):
        objective_true.add("fix_instructions_surgical")
    if bool(qa_report.get("pass_rewrite_needed")) and rewrite_actions and all(
        str(action.get("issue_code") or "").strip()
        and str(action.get("target") or "").strip()
        and str(action.get("action") or "").strip()
        and str(action.get("replacement_guidance") or "").strip()
        for action in rewrite_actions
    ):
        objective_true.add("rewrite_plan_actionable")
    if objective_true:
        result = _override_scores(
            result,
            force_true=objective_true,
            warning="deterministic_override:qa_objective_checks",
        )
    return result


async def judge_rewritten_draft(
    rewritten: dict[str, Any] | None,
    original_draft: dict[str, Any] | None,
    qa_report: dict[str, Any] | None,
    atoms: dict[str, Any] | None,
    *,
    cta_final_line: str,
    proof_gap: bool,
    openai: OpenAIClient,
    run_id: str | None = None,
    payload_id: str | None = None,
) -> dict[str, Any]:
    stage = "EMAIL_REWRITE"
    if not rewritten:
        return missing_artifact_result(stage, "artifact")

    rubric = """
1) high_issues_resolved: high-severity QA issues are addressed.
2) no_new_content: rewritten copy does not add unsupported claims.
3) untouched_sentences_preserved: unrelated passing sentences are preserved.
4) cta_exact: final line exactly matches locked CTA.
5) metadata_preserved: preset_id, selected_angle_id, used_hook_ids unchanged.
""".strip()

    examples = """
PASS metadata_preserved: preset and selected ids exactly unchanged.
FAIL metadata_preserved: rewritten draft changed selected_angle_id.
PASS cta_exact: final line exactly locked CTA.
FAIL cta_exact: CTA wording changed.
""".strip()

    result = await _run_stage_judge(
        stage=stage,
        artifacts={
            "artifact": rewritten,
            "original_draft": original_draft or {},
            "qa_report": qa_report or {},
            "atoms": atoms or {},
            "cta_final_line": cta_final_line,
            "proof_gap": bool(proof_gap),
        },
        rubric_text=rubric,
        examples_text=examples,
        openai=openai,
        run_id=run_id,
        payload_id=payload_id,
    )

    forced: list[tuple[str, str]] = []
    objective_true: set[str] = set()
    cta_lock = build_cta_lock(cta_final_line)
    last_line = normalize_cta_text(_extract_last_nonempty_line(str(rewritten.get("body") or "")))
    proof_basis = _proof_basis_for_artifact(
        proof_text=str((atoms or {}).get("proof_atom") or ""),
        proof_basis=dict((atoms or {}).get("proof_basis") or {}),
        brief={},
        selected_hook_id=str(((atoms or {}).get("used_hook_ids") or [""])[0] or ""),
        selected_fit_hypothesis_id=str((atoms or {}).get("selected_angle_id") or ""),
    )
    if last_line != cta_lock["final_line"]:
        forced.append(("cta_exact", "rewritten final line does not exactly match locked CTA"))
    else:
        objective_true.add("cta_exact")

    for key in ("preset_id", "selected_angle_id"):
        if str((rewritten or {}).get(key) or "") != str((original_draft or {}).get(key) or ""):
            forced.append(("metadata_preserved", f"metadata mismatch for {key}"))
            break

    rewritten_hooks = [str(item or "") for item in (rewritten or {}).get("used_hook_ids") or []]
    original_hooks = [str(item or "") for item in (original_draft or {}).get("used_hook_ids") or []]
    if rewritten_hooks != original_hooks:
        forced.append(("metadata_preserved", "used_hook_ids changed in rewritten draft"))

    if _has_weak_proof_basis(proof_basis, proof_gap=proof_gap) and runtime_contains_unsupported_proof_sentence(
        str(rewritten.get("body") or ""),
        cta_final_line=cta_lock["final_line"],
        message_atoms=atoms,
    ):
        forced.append(("no_new_content", "proof sentence introduced despite proof_gap"))

    result = _apply_failures(result, forced_failures=forced)
    if (
        str((rewritten or {}).get("preset_id") or "") == str((original_draft or {}).get("preset_id") or "")
        and str((rewritten or {}).get("selected_angle_id") or "") == str((original_draft or {}).get("selected_angle_id") or "")
        and rewritten_hooks == original_hooks
    ):
        objective_true.add("metadata_preserved")
    if _rewrite_high_issues_resolved(qa_report, original_draft, rewritten, cta_final_line=cta_final_line):
        objective_true.add("high_issues_resolved")
    if _rewrite_no_new_content(
        rewritten,
        proof_gap=_has_weak_proof_basis(proof_basis, proof_gap=proof_gap),
        atoms=atoms,
        cta_final_line=cta_lock["final_line"],
    ):
        objective_true.add("no_new_content")
    if _untouched_sentences_preserved(qa_report, original_draft, rewritten, cta_final_line=cta_lock["final_line"]):
        objective_true.add("untouched_sentences_preserved")
    else:
        result = _apply_failures(
            result,
            forced_failures=[("untouched_sentences_preserved", "untargeted original sentences were not preserved")],
        )
    if objective_true:
        result = _override_scores(
            result,
            force_true=objective_true,
            warning="deterministic_override:rewrite_objective_checks",
        )
    return result
