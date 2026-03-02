from __future__ import annotations

from collections import Counter
from typing import Any

from evals.models import EvalResult, JudgeSummary


def compute_judge_summary(
    *,
    results: list[EvalResult],
    model: str,
    mode: str,
    prompt_contract_hash: str,
    calibration: dict[str, Any] | None = None,
) -> tuple[JudgeSummary, list[dict[str, Any]]]:
    evaluated = [result for result in results if str(result.judge.get("status")) == "scored"]
    skipped = [result for result in results if str(result.judge.get("status")) != "scored"]
    passed = [result for result in evaluated if result.judge.get("pass_fail") == "pass"]
    failed = [result for result in evaluated if result.judge.get("pass_fail") == "fail"]

    overall_values = [float(result.judge.get("overall", 0.0)) for result in evaluated]
    credibility_values = [
        float((result.judge.get("scores") or {}).get("credibility_no_overclaim", 0.0))
        for result in evaluated
    ]

    flag_counts: Counter[str] = Counter()
    for result in failed:
        for flag in result.judge.get("flags", []):
            flag_counts[str(flag)] += 1

    evaluated_count = len(evaluated)
    passed_count = len(passed)
    failed_count = len(failed)
    pass_rate = (passed_count / evaluated_count) if evaluated_count else 0.0
    mean_overall = (sum(overall_values) / len(overall_values)) if overall_values else 0.0
    mean_credibility = (sum(credibility_values) / len(credibility_values)) if credibility_values else 0.0

    summary = JudgeSummary(
        enabled=True,
        model=model,
        mode=mode,
        evaluated_cases=evaluated_count,
        skipped_cases=len(skipped),
        passed_cases=passed_count,
        failed_cases=failed_count,
        pass_rate=round(pass_rate, 4),
        mean_overall=round(mean_overall, 4),
        mean_credibility=round(mean_credibility, 4),
        failure_count_by_flag={k: int(v) for k, v in sorted(flag_counts.items(), key=lambda item: (-item[1], item[0]))},
        prompt_contract_hash=prompt_contract_hash,
        calibration_examples=int((calibration or {}).get("examples", 0)),
        calibration_pass_fail_agreement=(calibration or {}).get("pass_fail_agreement"),
        calibration_score_rank_correlation=(calibration or {}).get("score_rank_correlation"),
    )

    top_flags = [
        {"flag": flag, "count": int(count)}
        for flag, count in flag_counts.most_common(10)
    ]
    return summary, top_flags


def actionable_feedback(result: EvalResult) -> list[str]:
    feedback: list[str] = []
    for violation in result.violations:
        feedback.append(f"Lock violation `{violation.code}`: {violation.reason}")
    if result.judge.get("status") == "scored" and result.judge.get("pass_fail") == "fail":
        for flag in result.judge.get("flags", []):
            feedback.append(f"Quality flag `{flag}` triggered.")
        for bullet in result.judge.get("rationale_bullets", [])[:3]:
            feedback.append(f"Judge rationale: {bullet}")
    return feedback[:6]

