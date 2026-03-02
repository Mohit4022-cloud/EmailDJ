from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate candidate quality against baseline judge reports.")
    parser.add_argument("--baseline-report", required=True)
    parser.add_argument("--candidate-report", required=True)
    parser.add_argument("--pairwise-report", default="")
    parser.add_argument("--pairwise-baseline-label", default="A")
    parser.add_argument("--pairwise-candidate-label", default="B")
    parser.add_argument("--max-regression", type=float, default=0.0)
    parser.add_argument("--allow-failures", action="store_true")
    return parser.parse_args()


def _load(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON report: {path}")
    return data


def _criterion_mean(report: dict[str, Any], criterion: str) -> float:
    values: list[float] = []
    for row in report.get("results", []):
        if not bool(row.get("passed", False)):
            continue
        judge = row.get("judge", {})
        if judge.get("status") != "scored":
            continue
        value = (judge.get("scores") or {}).get(criterion)
        if isinstance(value, (int, float)):
            values.append(float(value))
    return (sum(values) / len(values)) if values else 0.0


def _lock_pass_rate(report: dict[str, Any]) -> float:
    summary = report.get("summary", {})
    try:
        return float(summary.get("pass_rate", 0.0))
    except Exception:
        return 0.0


def main() -> int:
    args = _parse_args()
    baseline = _load(args.baseline_report)
    candidate = _load(args.candidate_report)

    base_relevance = _criterion_mean(baseline, "relevance_to_prospect")
    base_credibility = _criterion_mean(baseline, "credibility_no_overclaim")
    cand_relevance = _criterion_mean(candidate, "relevance_to_prospect")
    cand_credibility = _criterion_mean(candidate, "credibility_no_overclaim")

    base_lock = _lock_pass_rate(baseline)
    cand_lock = _lock_pass_rate(candidate)

    failures: list[str] = []
    if cand_lock + 1e-9 < base_lock:
        failures.append(f"Lock pass rate regressed: baseline={base_lock:.4f}, candidate={cand_lock:.4f}")
    if cand_relevance + args.max_regression < base_relevance:
        failures.append(
            f"Relevance regressed beyond tolerance: baseline={base_relevance:.3f}, candidate={cand_relevance:.3f}, tolerance={args.max_regression:.3f}"
        )
    if cand_credibility + args.max_regression < base_credibility:
        failures.append(
            f"Credibility regressed beyond tolerance: baseline={base_credibility:.3f}, candidate={cand_credibility:.3f}, tolerance={args.max_regression:.3f}"
        )

    if args.pairwise_report:
        pairwise = _load(args.pairwise_report)
        summary = pairwise.get("summary", {})
        wins_a = int(summary.get("wins_a", 0) or 0)
        wins_b = int(summary.get("wins_b", 0) or 0)
        if args.pairwise_baseline_label == "A" and args.pairwise_candidate_label == "B":
            if wins_b < wins_a:
                failures.append(f"Pairwise regression: candidate wins ({wins_b}) < baseline wins ({wins_a})")
        elif args.pairwise_baseline_label == "B" and args.pairwise_candidate_label == "A":
            if wins_a < wins_b:
                failures.append(f"Pairwise regression: candidate wins ({wins_a}) < baseline wins ({wins_b})")

    print("Judge Regression Gate")
    print(f"- Baseline lock pass rate: {base_lock:.4f}")
    print(f"- Candidate lock pass rate: {cand_lock:.4f}")
    print(f"- Baseline relevance mean: {base_relevance:.3f}")
    print(f"- Candidate relevance mean: {cand_relevance:.3f}")
    print(f"- Baseline credibility mean: {base_credibility:.3f}")
    print(f"- Candidate credibility mean: {cand_credibility:.3f}")
    if failures:
        print("- Result: FAIL")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print("- Result: PASS")

    if args.allow_failures:
        return 0
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

