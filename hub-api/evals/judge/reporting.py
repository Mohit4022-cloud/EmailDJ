from __future__ import annotations

from collections import Counter
from typing import Any

from evals.judge.rubric import PASS_THRESHOLD_CREDIBILITY, PASS_THRESHOLD_OVERALL
from evals.judge.schemas import JUDGE_SCHEMA_VERSION
from evals.models import EvalResult, JudgeSummary


_BINARY_REMEDIATIONS: dict[str, str] = {
    "overclaim_present": "Rewrite claims to hedged language, remove unsupported numbers, and avoid guarantees.",
    "filler_padding_present": "Compress body length by 20%, remove generic openers, and require one concrete prospect hook.",
    "clarity_violation_present": "Enforce structure: one-sentence opener, two bullets, and one explicit CTA on the final line.",
}

_FLAG_REMEDIATIONS: dict[str, str] = {
    "weak_cta": "Switch to a low-friction CTA template with one explicit ask and no alternate CTA wording.",
    "tone_mismatch": "Shift prompt tone instructions to professional-neutral and ban hype punctuation.",
    "insufficient_personalization": "Require one role-specific and one company-specific fact in the opening block.",
    "judge_pandering_detected": "Remove meta-evaluation language and constrain output to prospect-facing business value only.",
}

_RECOMMENDATION_FALLBACKS: list[tuple[str, str]] = [
    (
        "overclaim_present",
        "Keep explicit anti-overclaim prompt constraints: hedge uncertain claims and disallow guaranteed outcomes.",
    ),
    (
        "clarity_violation_present",
        "Keep structure constraints active: one-sentence opener, two bullets, and final-line CTA.",
    ),
    (
        "filler_padding_present",
        "Keep brevity constraints active: avoid generic openers and preserve one concrete prospect hook.",
    ),
]


def compute_judge_summary(
    *,
    results: list[EvalResult],
    model: str,
    model_version: str,
    mode: str,
    prompt_contract_hash: str,
    calibration: dict[str, Any] | None = None,
) -> tuple[JudgeSummary, list[dict[str, Any]]]:
    evaluated = [result for result in results if str(result.judge.get("status")) == "scored"]
    skipped = [result for result in results if str(result.judge.get("status")) != "scored"]
    passed = [result for result in evaluated if result.judge.get("pass_fail") == "pass"]
    failed = [result for result in evaluated if result.judge.get("pass_fail") == "fail"]

    overall_values = [float(result.judge.get("overall", 0.0)) for result in evaluated]
    relevance_values = [
        float((result.judge.get("scores") or {}).get("relevance_to_prospect", 0.0))
        for result in evaluated
    ]
    credibility_values = [
        float((result.judge.get("scores") or {}).get("credibility_no_overclaim", 0.0))
        for result in evaluated
    ]
    overclaim_fail_count = sum(
        1
        for result in evaluated
        if bool((result.judge.get("binary_checks") or {}).get("overclaim_present", False))
    )

    flag_counts: Counter[str] = Counter()
    for result in failed:
        for flag in result.judge.get("flags", []):
            flag_counts[str(flag)] += 1

    cache_lookups = 0
    cache_hits = 0
    for result in evaluated:
        cache_lookups += 1
        if bool(result.judge.get("cache_hit", False)):
            cache_hits += 1

    evaluated_count = len(evaluated)
    passed_count = len(passed)
    failed_count = len(failed)
    pass_rate = (passed_count / evaluated_count) if evaluated_count else 0.0
    mean_overall = (sum(overall_values) / len(overall_values)) if overall_values else 0.0
    mean_relevance = (sum(relevance_values) / len(relevance_values)) if relevance_values else 0.0
    mean_credibility = (sum(credibility_values) / len(credibility_values)) if credibility_values else 0.0

    summary = JudgeSummary(
        enabled=True,
        model=model,
        model_version=model_version,
        mode=mode,
        schema_version=(
            str((evaluated[0].judge or {}).get("schema_version", "")).strip()
            if evaluated
            else JUDGE_SCHEMA_VERSION
        )
        or JUDGE_SCHEMA_VERSION,
        evaluated_cases=evaluated_count,
        skipped_cases=len(skipped),
        passed_cases=passed_count,
        failed_cases=failed_count,
        pass_rate=round(pass_rate, 4),
        mean_overall=round(mean_overall, 4),
        mean_relevance=round(mean_relevance, 4),
        mean_credibility=round(mean_credibility, 4),
        overclaim_fail_count=int(overclaim_fail_count),
        failure_count_by_flag={k: int(v) for k, v in sorted(flag_counts.items(), key=lambda item: (-item[1], item[0]))},
        prompt_contract_hash=prompt_contract_hash,
        threshold_overall=PASS_THRESHOLD_OVERALL,
        threshold_credibility=PASS_THRESHOLD_CREDIBILITY,
        cache_hits=cache_hits,
        cache_lookups=cache_lookups,
        cache_hit_rate=round((cache_hits / cache_lookups), 4) if cache_lookups else 0.0,
        calibration_examples=int((calibration or {}).get("examples", 0)),
        calibration_pass_fail_agreement=(calibration or {}).get("pass_fail_agreement"),
        calibration_score_rank_correlation=(calibration or {}).get("score_rank_correlation"),
    )

    top_flags = [
        {"flag": flag, "count": int(count)}
        for flag, count in flag_counts.most_common(10)
    ]
    return summary, top_flags


def synthesize_prompt_adjustments(
    *,
    results: list[EvalResult],
    max_items: int = 3,
) -> list[dict[str, Any]]:
    if max_items < 1:
        return []

    scored = [result for result in results if str(result.judge.get("status")) == "scored"]
    binary_counts: Counter[str] = Counter()
    flag_counts: Counter[str] = Counter()

    for result in scored:
        binary_checks = result.judge.get("binary_checks") or {}
        for key in _BINARY_REMEDIATIONS:
            if bool(binary_checks.get(key, False)):
                binary_counts[key] += 1
        for flag in result.judge.get("flags", []):
            key = str(flag).strip()
            if key:
                flag_counts[key] += 1

    recommendations: list[dict[str, Any]] = []
    seen_keys: set[str] = set()

    for key in ("overclaim_present", "filler_padding_present", "clarity_violation_present"):
        count = int(binary_counts.get(key, 0))
        if count <= 0:
            continue
        recommendations.append(
            {
                "signal": key,
                "count": count,
                "action": _BINARY_REMEDIATIONS[key],
            }
        )
        seen_keys.add(key)
        if len(recommendations) >= max_items:
            return recommendations[:max_items]

    for flag, count in sorted(flag_counts.items(), key=lambda item: (-item[1], item[0])):
        if flag not in _FLAG_REMEDIATIONS:
            continue
        if flag in seen_keys:
            continue
        recommendations.append(
            {
                "signal": flag,
                "count": int(count),
                "action": _FLAG_REMEDIATIONS[flag],
            }
        )
        seen_keys.add(flag)
        if len(recommendations) >= max_items:
            return recommendations[:max_items]

    for key, action in _RECOMMENDATION_FALLBACKS:
        if len(recommendations) >= max(2, max_items):
            break
        if key in seen_keys:
            continue
        recommendations.append(
            {
                "signal": key,
                "count": int(binary_counts.get(key, 0)),
                "action": action,
            }
        )
        seen_keys.add(key)

    return recommendations[:max_items]


def actionable_feedback(result: EvalResult) -> list[str]:
    feedback: list[str] = []
    for violation in result.violations:
        feedback.append(f"Lock violation `{violation.code}`: {violation.reason}")
    if result.judge.get("status") == "scored" and result.judge.get("pass_fail") == "fail":
        for action in result.judge.get("repair_actions", []):
            if isinstance(action, dict):
                tag = str(action.get("tag", "")).strip()
                step = str(action.get("action", "")).strip()
                if tag and step:
                    feedback.append(f"{tag}: {step}")
        for flag in result.judge.get("flags", []):
            feedback.append(f"Quality flag `{flag}` triggered.")
        for bullet in result.judge.get("rationale_bullets", [])[:3]:
            feedback.append(f"Judge rationale: {bullet}")
    return feedback[:6]
