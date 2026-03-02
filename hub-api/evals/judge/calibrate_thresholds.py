from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.judge.cache import JudgeCache
from evals.judge.client import JudgeClient, JudgeRuntime
from evals.judge.reliability import calibration_metrics, load_calibration_set
from evals.judge.rubric import AUTO_FAIL_FLAGS, PASS_THRESHOLD_CREDIBILITY, PASS_THRESHOLD_OVERALL


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate judge pass/fail thresholds from labeled examples.")
    parser.add_argument("--calibration", default="evals/judge/calibration_set.v2.json")
    parser.add_argument("--out", default="reports/judge/calibration/latest.json")
    parser.add_argument("--changelog", default="reports/judge/calibration/threshold_changelog.jsonl")
    parser.add_argument("--judge-mode", choices=("mock", "real"), default=os.environ.get("EMAILDJ_JUDGE_MODE", "mock"))
    parser.add_argument("--judge-model", default=os.environ.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--judge-sample-count", type=int, default=int(os.environ.get("EMAILDJ_JUDGE_SAMPLE_COUNT", "1")))
    parser.add_argument("--judge-cache-dir", default="reports/judge/cache")
    parser.add_argument("--candidate-id", default="calibration")
    parser.add_argument("--target-criterion-agreement", type=float, default=0.65)
    return parser.parse_args()


def _predict_pass(*, row: dict[str, Any], overall_threshold: float, credibility_threshold: float) -> str:
    flags = set(row.get("flags", []))
    if any(flag in AUTO_FAIL_FLAGS for flag in flags):
        return "fail"
    overall = float(row.get("overall", 0.0))
    credibility = float((row.get("scores") or {}).get("credibility_no_overclaim", 0.0))
    if overall < overall_threshold:
        return "fail"
    if credibility < credibility_threshold:
        return "fail"
    return "pass"


def _accuracy(expected_rows: list[dict[str, Any]], predicted_rows: list[dict[str, Any]]) -> float:
    by_id = {str(row.get("id")): row for row in predicted_rows}
    compared = 0
    correct = 0
    for row in expected_rows:
        rid = str(row.get("id", "")).strip()
        if not rid or rid not in by_id:
            continue
        exp = str(row.get("expected_pass_fail", "")).strip().lower()
        pred = str(by_id[rid].get("pass_fail", "")).strip().lower()
        if exp not in {"pass", "fail"} or pred not in {"pass", "fail"}:
            continue
        compared += 1
        if exp == pred:
            correct += 1
    return (correct / compared) if compared else 0.0


def _criterion_label_agreement(expected_rows: list[dict[str, Any]], predicted_rows: list[dict[str, Any]]) -> dict[str, float]:
    by_id = {str(row.get("id")): row for row in predicted_rows}
    criteria = (
        "relevance_to_prospect",
        "clarity_and_structure",
        "credibility_no_overclaim",
        "personalization_quality",
        "cta_quality",
        "tone_match",
        "conciseness_signal_density",
        "value_prop_specificity",
    )
    out: dict[str, float] = {}
    for criterion in criteria:
        compared = 0
        match = 0
        for row in expected_rows:
            rid = str(row.get("id", "")).strip()
            if not rid or rid not in by_id:
                continue
            score = int((by_id[rid].get("scores") or {}).get(criterion, 0))
            expected_scores = row.get("expected_scores")
            if isinstance(expected_scores, dict) and isinstance(expected_scores.get(criterion), (int, float)):
                expected_score = float(expected_scores[criterion])
                compared += 1
                if abs(score - expected_score) <= 1.0:
                    match += 1
                continue

            expected_pf = str(row.get("expected_pass_fail", "")).strip().lower()
            if expected_pf not in {"pass", "fail"}:
                continue
            criterion_predicts_pass = score >= 4
            compared += 1
            if (criterion_predicts_pass and expected_pf == "pass") or (not criterion_predicts_pass and expected_pf == "fail"):
                match += 1
        out[criterion] = round((match / compared), 4) if compared else 0.0
    return out


def _expected_pass_rate(expected_rows: list[dict[str, Any]]) -> float:
    vals = [str(row.get("expected_pass_fail", "")).strip().lower() for row in expected_rows]
    labeled = [val for val in vals if val in {"pass", "fail"}]
    if not labeled:
        return 0.0
    return sum(1 for val in labeled if val == "pass") / len(labeled)


def _predicted_pass_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if str(row.get("pass_fail", "")).strip().lower() == "pass") / len(rows)


def _sweep_thresholds(expected_rows: list[dict[str, Any]], predicted_rows: list[dict[str, Any]]) -> dict[str, Any]:
    target_pass_rate = _expected_pass_rate(expected_rows)
    best: dict[str, Any] | None = None
    for overall_i in range(30, 46):
        for cred_i in range(35, 51):
            overall_threshold = round(overall_i / 10.0, 1)
            credibility_threshold = round(cred_i / 10.0, 1)
            modified = []
            for row in predicted_rows:
                candidate = dict(row)
                candidate["pass_fail"] = _predict_pass(
                    row=row,
                    overall_threshold=overall_threshold,
                    credibility_threshold=credibility_threshold,
                )
                modified.append(candidate)
            acc = _accuracy(expected_rows, modified)
            pass_rate_gap = abs(_predicted_pass_rate(modified) - target_pass_rate)
            candidate = {
                "overall_threshold": overall_threshold,
                "credibility_threshold": credibility_threshold,
                "accuracy": round(acc, 4),
                "pass_rate_gap": round(pass_rate_gap, 4),
            }
            if best is None:
                best = candidate
                continue
            # pick highest accuracy; tie-break toward matching labeled pass-rate profile; then stricter threshold.
            if candidate["accuracy"] > best["accuracy"]:
                best = candidate
            elif candidate["accuracy"] == best["accuracy"]:
                if candidate["pass_rate_gap"] < best["pass_rate_gap"]:
                    best = candidate
                elif candidate["pass_rate_gap"] == best["pass_rate_gap"]:
                    if candidate["credibility_threshold"] > best["credibility_threshold"]:
                        best = candidate
                    elif candidate["credibility_threshold"] == best["credibility_threshold"] and candidate["overall_threshold"] > best["overall_threshold"]:
                        best = candidate
    return best or {
        "overall_threshold": PASS_THRESHOLD_OVERALL,
        "credibility_threshold": PASS_THRESHOLD_CREDIBILITY,
        "accuracy": 0.0,
    }


def _threshold_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    rec = data.get("recommended_thresholds")
    if not isinstance(rec, dict):
        return None
    try:
        return {
            "overall": float(rec.get("overall")),
            "credibility": float(rec.get("credibility")),
        }
    except Exception:
        return None


def _append_changelog(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def main() -> int:
    args = _parse_args()
    expected_rows = load_calibration_set(args.calibration)
    cache = JudgeCache(Path(args.judge_cache_dir))
    client = JudgeClient(
        cache=cache,
        runtime=JudgeRuntime(
            mode=(args.judge_mode.strip().lower() or "mock"),
            model=(args.judge_model.strip() or "gpt-4.1-mini"),
            timeout_seconds=float(os.environ.get("EMAILDJ_JUDGE_TIMEOUT_SEC", "30")),
            sample_count=max(1, int(args.judge_sample_count)),
            secondary_model=(os.environ.get("EMAILDJ_JUDGE_SECONDARY_MODEL", "").strip() or None),
        ),
    )

    predicted_rows: list[dict[str, Any]] = []
    for row in expected_rows:
        rid = str(row.get("id", "")).strip()
        body = str(row.get("body", "")).strip()
        if not rid or not body:
            continue
        context = {
            "prospect_role": str(row.get("prospect_role", "")),
            "prospect_company": str(row.get("prospect_company", "")),
            "offer_lock": str(row.get("offer_lock", "")),
            "cta_lock": str(row.get("cta_lock", "")),
            "allowed_facts_summary": str(row.get("allowed_facts_summary", "")),
            "tone_target": str(row.get("tone_target", "professional, balanced")),
        }
        scored = client.evaluate_ad_hoc(
            case_id=rid,
            context=context,
            subject=str(row.get("subject", "")),
            body=body,
            candidate_id=args.candidate_id,
            eval_mode="calibration",
        )
        predicted_rows.append(
            {
                "id": rid,
                "pass_fail": scored.get("pass_fail", "fail"),
                "overall": scored.get("overall", 0.0),
                "scores": scored.get("scores", {}),
                "flags": scored.get("flags", []),
            }
        )

    base_metrics = calibration_metrics(expected=expected_rows, predicted=predicted_rows)
    best = _sweep_thresholds(expected_rows=expected_rows, predicted_rows=predicted_rows)

    adjusted_rows = []
    for row in predicted_rows:
        candidate = dict(row)
        candidate["pass_fail"] = _predict_pass(
            row=row,
            overall_threshold=best["overall_threshold"],
            credibility_threshold=best["credibility_threshold"],
        )
        adjusted_rows.append(candidate)
    tuned_metrics = calibration_metrics(expected=expected_rows, predicted=adjusted_rows)
    criterion_agreement = _criterion_label_agreement(expected_rows=expected_rows, predicted_rows=predicted_rows)
    previous = _threshold_snapshot(Path(args.out))
    weakest = sorted(
        [{"criterion": key, "agreement": value} for key, value in criterion_agreement.items()],
        key=lambda item: item["agreement"],
    )[:3]
    weakest_target_pass = all(float(item["agreement"]) >= float(args.target_criterion_agreement) for item in weakest)
    targeted_criteria = (
        "clarity_and_structure",
        "credibility_no_overclaim",
        "conciseness_signal_density",
    )
    targeted_criteria_meet_target = all(
        float(criterion_agreement.get(criterion, 0.0)) >= float(args.target_criterion_agreement)
        for criterion in targeted_criteria
    )

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "judge_mode": args.judge_mode,
        "judge_model": args.judge_model,
        "dataset": args.calibration,
        "examples": len(expected_rows),
        "current_thresholds": {
            "overall": PASS_THRESHOLD_OVERALL,
            "credibility": PASS_THRESHOLD_CREDIBILITY,
        },
        "recommended_thresholds": {
            "overall": best["overall_threshold"],
            "credibility": best["credibility_threshold"],
            "accuracy": best["accuracy"],
        },
        "current_metrics": base_metrics,
        "tuned_metrics": tuned_metrics,
        "criterion_label_agreement": criterion_agreement,
        "criterion_agreement_target": float(args.target_criterion_agreement),
        "weakest_criteria_meet_target": weakest_target_pass,
        "targeted_criteria": list(targeted_criteria),
        "targeted_criteria_meet_target": targeted_criteria_meet_target,
        "weakest_criteria": weakest,
        "stability": {
            "previous_recommended_thresholds": previous,
            "delta_overall": (
                round(best["overall_threshold"] - float(previous["overall"]), 3)
                if previous is not None
                else None
            ),
            "delta_credibility": (
                round(best["credibility_threshold"] - float(previous["credibility"]), 3)
                if previous is not None
                else None
            ),
        },
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    _append_changelog(
        Path(args.changelog),
        {
            "generated_at": result["generated_at"],
            "dataset": args.calibration,
            "examples": len(expected_rows),
            "judge_mode": args.judge_mode,
            "judge_model": args.judge_model,
            "recommended_thresholds": result["recommended_thresholds"],
            "previous_recommended_thresholds": previous,
            "delta_overall": result["stability"]["delta_overall"],
            "delta_credibility": result["stability"]["delta_credibility"],
            "current_pass_fail_agreement": base_metrics.get("pass_fail_agreement"),
            "tuned_pass_fail_agreement": tuned_metrics.get("pass_fail_agreement"),
            "score_rank_correlation": base_metrics.get("score_rank_correlation"),
            "weakest_criteria": result["weakest_criteria"],
            "criterion_agreement_target": result["criterion_agreement_target"],
            "weakest_criteria_meet_target": result["weakest_criteria_meet_target"],
            "targeted_criteria_meet_target": result["targeted_criteria_meet_target"],
        },
    )

    print("Judge Calibration")
    print(f"- Examples: {len(expected_rows)}")
    print(
        f"- Current thresholds: overall>={PASS_THRESHOLD_OVERALL:.1f}, credibility>={PASS_THRESHOLD_CREDIBILITY:.1f}"
    )
    print(
        f"- Recommended thresholds: overall>={best['overall_threshold']:.1f}, credibility>={best['credibility_threshold']:.1f}"
    )
    print(f"- Current pass/fail agreement: {base_metrics.get('pass_fail_agreement', 0):.2%}")
    print(f"- Tuned pass/fail agreement: {tuned_metrics.get('pass_fail_agreement', 0):.2%}")
    print(f"- Score rank correlation: {base_metrics.get('score_rank_correlation')}")
    if weakest:
        print("- Weakest criterion agreements:")
        for item in weakest:
            print(f"  - {item['criterion']}: {item['agreement']:.2%}")
        print(f"- Weakest criteria meet target {args.target_criterion_agreement:.2f}: {weakest_target_pass}")
    print(
        f"- Targeted criteria (clarity/credibility/conciseness) meet target {args.target_criterion_agreement:.2f}: "
        f"{targeted_criteria_meet_target}"
    )
    print(f"- Report: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
