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
)
from app.engine.schemas import JUDGE_RESULT_SCHEMA, RF_JUDGE_RESULT
from app.engine.stage_runner import _extract_message_text, _parse_message_content, _validate_schema
from app.engine.validators import ValidationIssue, validate_messaging_brief
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


def _append_unique(items: list[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


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
    return {
        "prospect": dict(payload.get("prospect") or {}),
        "user_company": dict(payload.get("user_company") or {}),
        "cta": dict(payload.get("cta") or {}),
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
    if has_mechanism and not (has_metric or has_time or has_outcome_verb):
        return False
    return has_metric or has_time or has_outcome_verb


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
    if ("make it" in lowered or "improve" in lowered) and not any(
        token in lowered for token in ("fact_id", "proof", "atom", "replace", "line", "sentence")
    ):
        return True
    return False


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
    seen_types: set[str] = set()
    seen_hooks: set[str] = set()
    for angle in angle_set.get("angles") or []:
        if not isinstance(angle, dict):
            continue
        angle_type = str(angle.get("angle_type") or "")
        hook_id = str(angle.get("selected_hook_id") or "")
        if angle_type and angle_type in seen_types:
            forced.append(("angles_distinct", f"duplicate angle_type '{angle_type}'"))
        if hook_id and hook_id in seen_hooks:
            forced.append(("angles_distinct", f"duplicate selected_hook_id '{hook_id}'"))
        seen_types.add(angle_type)
        seen_hooks.add(hook_id)
        cta = str(angle.get("cta_question_suggestion") or "").strip()
        if cta and (not cta.endswith("?") or len(cta) > 160):
            forced.append(("cta_bridge_natural", "cta_question_suggestion must be <=160 chars and end with ?"))

    return _apply_failures(result, forced_failures=forced)


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
    opener_line = str(atoms.get("opener_atom") or "")
    value_line = str(atoms.get("value_atom") or "")
    proof_line = str(atoms.get("proof_atom") or "")
    cta_line = str(atoms.get("cta_atom") or "")
    required_cta_line = str(atoms.get("required_cta_line") or "")

    if _check_bracket_placeholder(opener_line) or _check_bracket_placeholder(value_line):
        forced.append(("value_outcome_not_mechanism", "placeholder bracket token leaked in atoms"))

    if not _check_outcome_like(value_line):
        forced.append(("value_outcome_not_mechanism", "value_line describes mechanism without concrete outcome"))

    if proof_line and _proof_looks_circular(proof_line, brief or {}, angle=angle or {}):
        forced.append(("proof_not_circular", "proof_line appears circular or prospect-derived"))

    if cta_line.strip() != str(locked_cta or "").strip() or required_cta_line.strip() != str(locked_cta or "").strip():
        forced.append(("cta_locked", "atoms CTA fields do not match locked CTA"))

    comma_count = opener_line.count(",")
    connector_count = len(re.findall(r"\b(which|that|because|so|and)\b", opener_line.lower()))
    if comma_count > 1 or connector_count > 1:
        forced.append(("opener_simple", "opener contains too many clauses"))

    hook_ids = {str(item.get("hook_id") or "") for item in (brief or {}).get("hooks") or [] if isinstance(item, dict)}
    used_hook_ids = [str(item or "") for item in atoms.get("used_hook_ids") or []]
    if any(hook_id and hook_id not in hook_ids for hook_id in used_hook_ids):
        forced.append(("hook_ids_valid", "used_hook_ids contains unknown hook id"))

    return _apply_failures(result, forced_failures=forced)


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
    subject = str(draft.get("subject") or "").strip()
    body = str(draft.get("body") or "")
    last_line = _extract_last_nonempty_line(body)

    if len(subject) > 70:
        forced.append(("subject_length", "subject exceeds 70 characters"))

    if last_line != str(cta_final_line or "").strip():
        forced.append(("cta_exact", "final body line does not exactly match locked CTA"))

    lowered_text = f"{subject}\n{body}".lower()
    for banned in BANNED_PHRASES:
        if banned in lowered_text:
            forced.append(("no_banned_phrases", f"contains banned phrase '{banned}'"))
            break

    if _count_questions(body) != 1:
        forced.append(("no_double_cta", "body must contain exactly one question mark"))

    proof_atom_missing = str((atoms or {}).get("proof_atom") or "").strip() == ""
    if proof_gap and proof_atom_missing and "peer" in body.lower():
        forced.append(("proof_respected", "proof sentence appears despite proof_gap"))

    return _apply_failures(result, forced_failures=forced)


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

    for issue in issues:
        if not isinstance(issue, dict):
            continue
        evidence = _as_list_of_strings(issue.get("evidence"))
        if not evidence or not all(snippet in draft_blob for snippet in evidence):
            forced.append(("evidence_quoted", "issue evidence is not directly quoted from draft"))
        fix_instruction = str(issue.get("fix_instruction") or "")
        if _non_actionable_fix_instruction(fix_instruction):
            forced.append(("fix_instructions_surgical", "fix_instruction is directional but not surgical"))

    if bool(qa_report.get("pass_rewrite_needed")) and not _as_list_of_strings(qa_report.get("rewrite_plan")):
        forced.append(("rewrite_plan_actionable", "pass_rewrite_needed true but rewrite_plan is empty"))

    return _apply_failures(result, forced_failures=forced)


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
    last_line = _extract_last_nonempty_line(str(rewritten.get("body") or ""))
    if last_line != str(cta_final_line or "").strip():
        forced.append(("cta_exact", "rewritten final line does not exactly match locked CTA"))

    for key in ("preset_id", "selected_angle_id"):
        if str((rewritten or {}).get(key) or "") != str((original_draft or {}).get(key) or ""):
            forced.append(("metadata_preserved", f"metadata mismatch for {key}"))
            break

    rewritten_hooks = [str(item or "") for item in (rewritten or {}).get("used_hook_ids") or []]
    original_hooks = [str(item or "") for item in (original_draft or {}).get("used_hook_ids") or []]
    if rewritten_hooks != original_hooks:
        forced.append(("metadata_preserved", "used_hook_ids changed in rewritten draft"))

    proof_atom_missing = str((atoms or {}).get("proof_atom") or "").strip() == ""
    if proof_gap and proof_atom_missing and "peer" in str(rewritten.get("body") or "").lower():
        forced.append(("no_new_content", "proof sentence introduced despite proof_gap"))

    return _apply_failures(result, forced_failures=forced)
