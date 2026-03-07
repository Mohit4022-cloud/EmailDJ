from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.judge.cache import JudgeCache
from evals.judge.client import JudgeClient, JudgeRuntime
from evals.judge.redaction import redact_text


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run judge evaluation on an anonymized real-world corpus.")
    parser.add_argument("--dataset", default="evals/judge/real_corpus.v1.json")
    parser.add_argument("--report-dir", default="reports/judge/real_corpus")
    parser.add_argument("--judge-mode", choices=("mock", "real"), default=os.environ.get("EMAILDJ_JUDGE_MODE", "mock"))
    parser.add_argument("--judge-model", default=os.environ.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-mini"))
    parser.add_argument(
        "--judge-model-version",
        default=(
            os.environ.get("EMAILDJ_JUDGE_MODEL_VERSION", "").strip()
            or os.environ.get("EMAILDJ_JUDGE_MODEL", "gpt-4.1-mini").strip()
            or "gpt-4.1-mini"
        ),
    )
    parser.add_argument("--judge-sample-count", type=int, default=int(os.environ.get("EMAILDJ_JUDGE_SAMPLE_COUNT", "1")))
    parser.add_argument("--judge-cache-dir", default="reports/judge/cache")
    parser.add_argument("--allow-failures", action="store_true")
    return parser.parse_args()


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Real corpus dataset must be a list.")
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _safe_quality(value: Any) -> str:
    quality = str(value or "").strip().lower()
    if quality in {"good", "ok", "bad"}:
        return quality
    return ""


def _expected_pass_from_quality(quality: str) -> str:
    if quality == "bad":
        return "fail"
    if quality in {"good", "ok"}:
        return "pass"
    return ""


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _f1(precision: float, recall: float) -> float:
    if precision <= 0 or recall <= 0:
        return 0.0
    return (2.0 * precision * recall) / (precision + recall)


def _to_md(payload: dict[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines: list[str] = []
    lines.append("# Judge Real Corpus Report")
    lines.append("")
    lines.append(f"- Generated at: `{payload.get('generated_at', '')}`")
    lines.append(f"- Judge model: `{payload.get('judge_model', 'unknown')}`")
    lines.append(f"- Judge model version: `{payload.get('judge_model_version', 'unknown')}`")
    lines.append(f"- Judge mode: `{payload.get('judge_mode', 'unknown')}`")
    lines.append(f"- Dataset: `{payload.get('dataset', '')}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total cases | {int(summary.get('total_cases', 0))} |")
    lines.append(f"| Scored cases | {int(summary.get('scored_cases', 0))} |")
    lines.append(f"| Quality label agreement | {float(summary.get('quality_label_agreement', 0.0)):.2%} |")
    lines.append(f"| Overclaim precision | {float(summary.get('overclaim_precision', 0.0)):.2%} |")
    lines.append(f"| Overclaim recall | {float(summary.get('overclaim_recall', 0.0)):.2%} |")
    lines.append(f"| Overclaim F1 | {float(summary.get('overclaim_f1', 0.0)):.2%} |")
    lines.append("")
    lines.append("## Notable Mismatches")
    lines.append("")
    mismatches = payload.get("mismatches", [])
    if mismatches:
        lines.append("| ID | Expected | Predicted | Overclaim label | Overclaim predicted | Snippet |")
        lines.append("|---|---|---|---|---|---|")
        for row in mismatches[:10]:
            lines.append(
                "| {id} | {expected} | {predicted} | {label} | {pred} | {snippet} |".format(
                    id=row.get("id", "unknown"),
                    expected=row.get("expected_pass_fail", "n/a"),
                    predicted=row.get("predicted_pass_fail", "n/a"),
                    label=row.get("label_overclaim"),
                    pred=row.get("predicted_overclaim"),
                    snippet=str(row.get("body_snippet", "")).replace("|", "/"),
                )
            )
    else:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    dataset_path = Path(args.dataset)
    rows = _load_dataset(dataset_path)
    cache = JudgeCache(Path(args.judge_cache_dir))
    client = JudgeClient(
        cache=cache,
        runtime=JudgeRuntime(
            mode=(args.judge_mode.strip().lower() or "mock"),
            model=(args.judge_model.strip() or "gpt-4.1-mini"),
            timeout_seconds=float(os.environ.get("EMAILDJ_JUDGE_TIMEOUT_SEC", "30")),
            sample_count=max(1, int(args.judge_sample_count)),
            model_version=(args.judge_model_version.strip() or args.judge_model.strip() or "gpt-4.1-mini"),
            secondary_model=(os.environ.get("EMAILDJ_JUDGE_SECONDARY_MODEL", "").strip() or None),
        ),
    )

    scored_rows: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    quality_compared = 0
    quality_matches = 0
    tp = fp = tn = fn = 0

    for row in rows:
        case_id = str(row.get("id", "")).strip()
        body = redact_text(str(row.get("body", "")))
        if not case_id or not body:
            continue
        subject = redact_text(str(row.get("subject", "")))
        context = {
            "prospect_role": redact_text(str(row.get("prospect_role", "Unknown role"))),
            "prospect_company": redact_text(str(row.get("prospect_company", "Unknown company"))),
            "offer_lock": redact_text(str(row.get("offer_lock", "Locked offer not specified"))),
            "cta_lock": redact_text(str(row.get("cta_lock", "Open to a 15-min chat next week?"))),
            "allowed_facts_summary": redact_text(str(row.get("allowed_facts_summary", ""))),
            "tone_target": redact_text(str(row.get("tone_target", "professional, balanced"))),
        }
        judged = client.evaluate_ad_hoc(
            case_id=case_id,
            context=context,
            subject=subject,
            body=body,
            candidate_id="real_corpus",
            eval_mode="real_corpus",
        )

        quality = _safe_quality(((row.get("labels") or {}).get("quality")))
        expected_pf = _expected_pass_from_quality(quality)
        predicted_pf = str(judged.get("pass_fail", "fail")).strip().lower() or "fail"
        if expected_pf in {"pass", "fail"}:
            quality_compared += 1
            if expected_pf == predicted_pf:
                quality_matches += 1

        label_overclaim = _safe_bool((row.get("labels") or {}).get("overclaim_present"))
        predicted_overclaim = bool((judged.get("binary_checks") or {}).get("overclaim_present", False))
        if label_overclaim is not None:
            if label_overclaim and predicted_overclaim:
                tp += 1
            elif label_overclaim and (not predicted_overclaim):
                fn += 1
            elif (not label_overclaim) and predicted_overclaim:
                fp += 1
            else:
                tn += 1

        scored_rows.append(
            {
                "id": case_id,
                "quality_label": quality,
                "expected_pass_fail": expected_pf,
                "predicted_pass_fail": predicted_pf,
                "label_overclaim": label_overclaim,
                "predicted_overclaim": predicted_overclaim,
                "overall": judged.get("overall", 0.0),
                "flags": judged.get("flags", []),
                "body_snippet": " ".join(body.split())[:140],
            }
        )

    precision = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
    recall = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
    quality_label_agreement = (quality_matches / quality_compared) if quality_compared else 0.0
    overclaim_f1 = _f1(precision, recall)

    for row in scored_rows:
        quality_mismatch = row.get("expected_pass_fail") in {"pass", "fail"} and row.get("expected_pass_fail") != row.get(
            "predicted_pass_fail"
        )
        overclaim_mismatch = (
            isinstance(row.get("label_overclaim"), bool) and bool(row.get("label_overclaim")) != bool(row.get("predicted_overclaim"))
        )
        if quality_mismatch or overclaim_mismatch:
            mismatches.append(row)
    mismatches.sort(key=lambda row: (row.get("id", "")))

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": str(dataset_path),
        "judge_mode": args.judge_mode,
        "judge_model": args.judge_model,
        "judge_model_version": args.judge_model_version,
        "summary": {
            "total_cases": len(rows),
            "scored_cases": len(scored_rows),
            "quality_compared": quality_compared,
            "quality_label_agreement": round(quality_label_agreement, 4),
            "overclaim_precision": round(precision, 4),
            "overclaim_recall": round(recall, 4),
            "overclaim_f1": round(overclaim_f1, 4),
            "overclaim_confusion": {
                "tp": tp,
                "fp": fp,
                "tn": tn,
                "fn": fn,
            },
        },
        "mismatches": mismatches[:20],
        "results": scored_rows,
    }

    out_dir = Path(args.report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"
    latest_json.write_text(json.dumps(out, indent=2), encoding="utf-8")
    latest_md.write_text(_to_md(out), encoding="utf-8")

    print("Judge Real Corpus")
    print(f"- Cases: {len(rows)}")
    print(f"- Scored: {len(scored_rows)}")
    print(f"- Quality agreement: {quality_label_agreement:.2%}")
    print(f"- Overclaim precision: {precision:.2%}")
    print(f"- Overclaim recall: {recall:.2%}")
    print(f"- Report: {latest_json}")

    if args.allow_failures:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
