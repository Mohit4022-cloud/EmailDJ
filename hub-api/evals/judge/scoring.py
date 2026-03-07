from __future__ import annotations

from statistics import median
from typing import Any

from evals.judge.rubric import CRITERIA, should_pass, weighted_overall


def normalize_scored_output(output: dict[str, Any]) -> dict[str, Any]:
    scores = {criterion: int(output["scores"][criterion]) for criterion in CRITERIA}
    binary_checks = _normalize_binary_checks(output.get("binary_checks"))
    flags = _normalize_flags(output.get("flags", []), binary_checks=binary_checks)
    overall = weighted_overall(scores)
    pass_fail = "pass" if should_pass(scores=scores, overall=overall, flags=flags) else "fail"
    rationale = [str(item).strip() for item in output.get("rationale_bullets", []) if str(item).strip()]
    if len(rationale) < 3:
        rationale = (rationale + ["Quality assessment completed."])[:3]
    return {
        "scores": scores,
        "binary_checks": binary_checks,
        "overall": overall,
        "pass_fail": pass_fail,
        "rationale_bullets": rationale[:6],
        "flags": flags,
    }


def aggregate_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {
            "scores": {criterion: 0 for criterion in CRITERIA},
            "binary_checks": {
                "overclaim_present": False,
                "filler_padding_present": False,
                "clarity_violation_present": False,
            },
            "overall": 0.0,
            "pass_fail": "fail",
            "rationale_bullets": ["No judge samples available."],
            "flags": ["auto_fail_policy_or_compliance_risk"],
            "sample_count": 0,
        }

    criterion_values: dict[str, list[int]] = {criterion: [] for criterion in CRITERIA}
    flags: list[str] = []
    rationales: list[str] = []
    binary_votes = {
        "overclaim_present": 0,
        "filler_padding_present": 0,
        "clarity_violation_present": 0,
    }
    pass_votes = 0

    for sample in samples:
        for criterion in CRITERIA:
            criterion_values[criterion].append(int(sample["scores"][criterion]))
        sample_binary = _normalize_binary_checks(sample.get("binary_checks"))
        for key, value in sample_binary.items():
            if value:
                binary_votes[key] += 1
        flags.extend(sample.get("flags", []))
        rationales.extend(sample.get("rationale_bullets", []))
        if str(sample.get("pass_fail", "")).lower() == "pass":
            pass_votes += 1

    majority = (len(samples) // 2) + 1
    aggregated_binary_checks = {
        key: count >= majority
        for key, count in binary_votes.items()
    }

    aggregated_scores = {
        criterion: int(round(float(median(values)))) if values else 0
        for criterion, values in criterion_values.items()
    }
    aggregated_overall = weighted_overall(aggregated_scores)
    aggregated_flags = _normalize_flags(flags, binary_checks=aggregated_binary_checks)
    pass_fail = "pass" if should_pass(aggregated_scores, aggregated_overall, aggregated_flags) else "fail"
    # Majority vote can only downgrade if median-based pass is borderline.
    if pass_votes < (len(samples) // 2 + 1):
        pass_fail = "fail"
    return {
        "scores": aggregated_scores,
        "binary_checks": aggregated_binary_checks,
        "overall": aggregated_overall,
        "pass_fail": pass_fail,
        "rationale_bullets": _unique([r for r in rationales if r])[:6] or ["Quality assessment completed."],
        "flags": aggregated_flags,
        "sample_count": len(samples),
    }


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(key)
    return output


def _normalize_binary_checks(raw: Any) -> dict[str, bool]:
    payload = raw if isinstance(raw, dict) else {}
    return {
        "overclaim_present": bool(payload.get("overclaim_present", False)),
        "filler_padding_present": bool(payload.get("filler_padding_present", False)),
        "clarity_violation_present": bool(payload.get("clarity_violation_present", False)),
    }


def _normalize_flags(raw_flags: Any, *, binary_checks: dict[str, bool]) -> list[str]:
    flags = _unique([str(value).strip() for value in (raw_flags or []) if str(value).strip()])
    if binary_checks.get("overclaim_present", False) and "auto_fail_overclaim_present" not in flags:
        flags.append("auto_fail_overclaim_present")
    if binary_checks.get("filler_padding_present", False) and "verbosity_padding_detected" not in flags:
        flags.append("verbosity_padding_detected")
    if binary_checks.get("clarity_violation_present", False) and "clarity_violation_detected" not in flags:
        flags.append("clarity_violation_detected")
    return flags
