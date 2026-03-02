from __future__ import annotations

import json
import re
from typing import Any

from evals.judge.rubric import ALL_FLAGS, CRITERIA

JUDGE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["scores", "overall", "pass_fail", "rationale_bullets", "flags"],
    "properties": {
        "scores": {
            "type": "object",
            "additionalProperties": False,
            "required": list(CRITERIA),
        },
        "overall": {"type": "number", "minimum": 0, "maximum": 5},
        "pass_fail": {"type": "string", "enum": ["pass", "fail"]},
        "rationale_bullets": {"type": "array"},
        "flags": {"type": "array"},
    },
}

PAIRWISE_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["winner", "confidence", "rationale_bullets", "flags"],
    "properties": {
        "winner": {"type": "string", "enum": ["A", "B", "tie"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "rationale_bullets": {"type": "array"},
        "flags": {"type": "array"},
    },
}


def _parse_json_candidate(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty_judge_output")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
            parsed = json.loads(text)
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("judge_output_missing_json_object") from None
            parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("judge_output_not_object")
    return parsed


def validate_judge_output(raw: dict[str, Any] | str) -> dict[str, Any]:
    payload = _parse_json_candidate(raw) if isinstance(raw, str) else dict(raw)
    scores = payload.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("judge_scores_missing")

    normalized_scores: dict[str, int] = {}
    for criterion in CRITERIA:
        value = scores.get(criterion)
        if not isinstance(value, (int, float)):
            raise ValueError(f"judge_score_invalid:{criterion}")
        ivalue = int(round(float(value)))
        if ivalue < 0 or ivalue > 5:
            raise ValueError(f"judge_score_out_of_range:{criterion}")
        normalized_scores[criterion] = ivalue

    overall = payload.get("overall")
    if not isinstance(overall, (int, float)):
        raise ValueError("judge_overall_missing")
    overall_f = float(overall)
    if overall_f < 0 or overall_f > 5:
        raise ValueError("judge_overall_out_of_range")

    pass_fail = str(payload.get("pass_fail", "")).strip().lower()
    if pass_fail not in {"pass", "fail"}:
        raise ValueError("judge_pass_fail_invalid")

    rationale = payload.get("rationale_bullets")
    if not isinstance(rationale, list):
        raise ValueError("judge_rationale_invalid")
    normalized_rationale = [str(item).strip() for item in rationale if str(item).strip()]
    if len(normalized_rationale) < 1:
        raise ValueError("judge_rationale_empty")

    flags_raw = payload.get("flags")
    if not isinstance(flags_raw, list):
        raise ValueError("judge_flags_invalid")
    flags: list[str] = []
    for item in flags_raw:
        value = str(item).strip()
        if not value:
            continue
        if value in ALL_FLAGS and value not in flags:
            flags.append(value)

    return {
        "scores": normalized_scores,
        "overall": round(overall_f, 4),
        "pass_fail": pass_fail,
        "rationale_bullets": normalized_rationale[:6],
        "flags": flags,
    }


def validate_pairwise_output(raw: dict[str, Any] | str) -> dict[str, Any]:
    payload = _parse_json_candidate(raw) if isinstance(raw, str) else dict(raw)
    winner = str(payload.get("winner", "")).strip()
    if winner not in {"A", "B", "tie"}:
        raise ValueError("pairwise_winner_invalid")

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)):
        raise ValueError("pairwise_confidence_invalid")
    confidence_f = max(0.0, min(1.0, float(confidence)))

    rationale_raw = payload.get("rationale_bullets")
    if not isinstance(rationale_raw, list):
        raise ValueError("pairwise_rationale_invalid")
    rationale = [str(item).strip() for item in rationale_raw if str(item).strip()]
    if not rationale:
        rationale = ["Pairwise comparison completed."]

    flags_raw = payload.get("flags")
    if not isinstance(flags_raw, list):
        raise ValueError("pairwise_flags_invalid")
    flags = [str(item).strip() for item in flags_raw if str(item).strip() in ALL_FLAGS]

    return {
        "winner": winner,
        "confidence": round(confidence_f, 4),
        "rationale_bullets": rationale[:6],
        "flags": flags,
    }

