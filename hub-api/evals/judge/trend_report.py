from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


RISING_SIGNAL_KEYS = (
    "filler_padding_present",
    "verbosity_padding_detected",
    "clarity_violation_present",
    "clarity_violation_detected",
    "judge_pandering_detected",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build judge trend deltas from commit-scoped artifacts.")
    parser.add_argument("--artifact-root", default="reports/judge/artifacts")
    parser.add_argument("--mode", default="full")
    parser.add_argument("--limit", type=int, default=14)
    parser.add_argument("--out-json", default="reports/judge/trend/latest.json")
    parser.add_argument("--out-md", default="reports/judge/trend/latest.md")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid JSON report: {path}")
    return raw


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _snippet(text: str, max_len: int = 140) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3].rstrip() + "..."


def _extract_row(candidate_dir: Path, mode: str) -> dict[str, Any] | None:
    report_path = candidate_dir / f"{mode}.json"
    meta_path = candidate_dir / "meta.json"
    if not report_path.exists():
        return None
    report = _load_json(report_path)
    summary = (report.get("judge") or {}).get("summary") or {}
    if not isinstance(summary, dict):
        return None

    meta: dict[str, Any] = {}
    if meta_path.exists():
        try:
            parsed = _load_json(meta_path)
            if isinstance(parsed, dict):
                meta = parsed
        except Exception:
            meta = {}

    scored_rows: list[dict[str, Any]] = []
    relevance_values: list[float] = []
    credibility_values: list[float] = []
    overclaim_fail_count = 0
    signal_counts: Counter[str] = Counter()

    for item in report.get("results", []):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", "")).strip()
        judge = item.get("judge") or {}
        if str(judge.get("status")) != "scored":
            continue
        scores = judge.get("scores") or {}
        binary_checks = judge.get("binary_checks") or {}
        flags = [str(flag).strip() for flag in judge.get("flags", []) if str(flag).strip()]
        relevance = _float(scores.get("relevance_to_prospect"), 0.0)
        credibility = _float(scores.get("credibility_no_overclaim"), 0.0)
        relevance_values.append(relevance)
        credibility_values.append(credibility)
        if bool(binary_checks.get("overclaim_present", False)):
            overclaim_fail_count += 1
        if bool(binary_checks.get("filler_padding_present", False)):
            signal_counts["filler_padding_present"] += 1
        if bool(binary_checks.get("clarity_violation_present", False)):
            signal_counts["clarity_violation_present"] += 1
        for flag in flags:
            if flag in RISING_SIGNAL_KEYS:
                signal_counts[flag] += 1

        scored_rows.append(
            {
                "id": case_id,
                "overall": _float(judge.get("overall"), 0.0),
                "relevance": relevance,
                "credibility": credibility,
                "pass_fail": str(judge.get("pass_fail", "fail")).strip().lower() or "fail",
                "body_snippet": _snippet(str(item.get("body", ""))),
                "rationale": str((judge.get("rationale_bullets") or [""])[0]).strip(),
            }
        )

    relevance_mean = (sum(relevance_values) / len(relevance_values)) if relevance_values else 0.0
    credibility_mean = (sum(credibility_values) / len(credibility_values)) if credibility_values else 0.0

    return {
        "candidate_id": candidate_dir.name,
        "artifact": str(report_path),
        "generated_at": report.get("generated_at"),
        "judge_model": summary.get("model"),
        "judge_model_version": summary.get("model_version", summary.get("model")),
        "judge_mode": summary.get("mode"),
        "prompt_contract_hash": summary.get("prompt_contract_hash"),
        "overall_mean": _float(summary.get("mean_overall"), 0.0),
        "relevance_mean": round(relevance_mean, 4),
        "credibility_mean": _float(summary.get("mean_credibility"), credibility_mean),
        "overclaim_fail_count": int(summary.get("overclaim_fail_count", overclaim_fail_count)),
        "pass_rate": _float(summary.get("pass_rate"), 0.0),
        "evaluated_cases": int(summary.get("evaluated_cases", len(scored_rows)) or 0),
        "failure_signal_counts": {key: int(signal_counts.get(key, 0)) for key in RISING_SIGNAL_KEYS},
        "cases": scored_rows,
        "recommended_prompt_adjustments": (report.get("judge") or {}).get("recommended_prompt_adjustments", []),
        "meta_generated_at": meta.get("generated_at"),
    }


def _compute_row_deltas(rows: list[dict[str, Any]]) -> None:
    prev: dict[str, Any] | None = None
    for row in rows:
        if prev is None:
            row["delta_overall"] = 0.0
            row["delta_relevance"] = 0.0
            row["delta_credibility"] = 0.0
            row["delta_overclaim_fail_count"] = 0
            row["delta_pass_rate"] = 0.0
        else:
            row["delta_overall"] = round(_float(row.get("overall_mean")) - _float(prev.get("overall_mean")), 4)
            row["delta_relevance"] = round(_float(row.get("relevance_mean")) - _float(prev.get("relevance_mean")), 4)
            row["delta_credibility"] = round(
                _float(row.get("credibility_mean")) - _float(prev.get("credibility_mean")),
                4,
            )
            row["delta_overclaim_fail_count"] = int(row.get("overclaim_fail_count", 0)) - int(
                prev.get("overclaim_fail_count", 0)
            )
            row["delta_pass_rate"] = round(_float(row.get("pass_rate")) - _float(prev.get("pass_rate")), 4)
        prev = row


def _most_regressed_cases(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, Any]]:
    prev_by_id = {
        str(item.get("id")): item
        for item in previous.get("cases", [])
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    rows: list[dict[str, Any]] = []
    for item in current.get("cases", []):
        if not isinstance(item, dict):
            continue
        case_id = str(item.get("id", "")).strip()
        if not case_id or case_id not in prev_by_id:
            continue
        prev = prev_by_id[case_id]
        d_overall = round(_float(item.get("overall")) - _float(prev.get("overall")), 4)
        d_relevance = round(_float(item.get("relevance")) - _float(prev.get("relevance")), 4)
        d_cred = round(_float(item.get("credibility")) - _float(prev.get("credibility")), 4)
        if d_overall >= 0 and d_relevance >= 0 and d_cred >= 0:
            continue
        prev_pf = str(prev.get("pass_fail", "fail")).strip().lower() or "fail"
        curr_pf = str(item.get("pass_fail", "fail")).strip().lower() or "fail"
        rows.append(
            {
                "id": case_id,
                "delta_overall": d_overall,
                "delta_relevance": d_relevance,
                "delta_credibility": d_cred,
                "pass_fail_transition": f"{prev_pf}->{curr_pf}",
                "snippet": str(item.get("body_snippet", "")),
                "rationale": str(item.get("rationale", "")),
            }
        )
    rows.sort(
        key=lambda item: (
            _float(item.get("delta_overall")),
            _float(item.get("delta_credibility")),
            _float(item.get("delta_relevance")),
            str(item.get("id", "")),
        )
    )
    return rows[:10]


def _rising_failure_flags(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, Any]]:
    curr_counts = current.get("failure_signal_counts") or {}
    prev_counts = previous.get("failure_signal_counts") or {}
    rows: list[dict[str, Any]] = []
    for key in RISING_SIGNAL_KEYS:
        curr = int(curr_counts.get(key, 0) or 0)
        prev = int(prev_counts.get(key, 0) or 0)
        delta = curr - prev
        if delta <= 0:
            continue
        rows.append(
            {
                "signal": key,
                "delta": delta,
                "current_count": curr,
                "previous_count": prev,
            }
        )
    rows.sort(key=lambda item: (-int(item.get("delta", 0)), str(item.get("signal", ""))))
    return rows[:5]


def _current_vs_previous(current: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    return {
        "current_candidate_id": current.get("candidate_id"),
        "previous_candidate_id": previous.get("candidate_id"),
        "metrics": [
            {
                "metric": "overall_mean",
                "current": round(_float(current.get("overall_mean")), 4),
                "previous": round(_float(previous.get("overall_mean")), 4),
                "delta": round(_float(current.get("overall_mean")) - _float(previous.get("overall_mean")), 4),
            },
            {
                "metric": "relevance_mean",
                "current": round(_float(current.get("relevance_mean")), 4),
                "previous": round(_float(previous.get("relevance_mean")), 4),
                "delta": round(_float(current.get("relevance_mean")) - _float(previous.get("relevance_mean")), 4),
            },
            {
                "metric": "credibility_mean",
                "current": round(_float(current.get("credibility_mean")), 4),
                "previous": round(_float(previous.get("credibility_mean")), 4),
                "delta": round(_float(current.get("credibility_mean")) - _float(previous.get("credibility_mean")), 4),
            },
            {
                "metric": "overclaim_fail_count",
                "current": int(current.get("overclaim_fail_count", 0) or 0),
                "previous": int(previous.get("overclaim_fail_count", 0) or 0),
                "delta": int(current.get("overclaim_fail_count", 0) or 0)
                - int(previous.get("overclaim_fail_count", 0) or 0),
            },
            {
                "metric": "pass_rate",
                "current": round(_float(current.get("pass_rate")), 4),
                "previous": round(_float(previous.get("pass_rate")), 4),
                "delta": round(_float(current.get("pass_rate")) - _float(previous.get("pass_rate")), 4),
            },
        ],
    }


def _to_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Judge Trend Report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Mode: `{payload['mode']}`")
    lines.append(f"- Samples: `{payload['count']}`")
    lines.append("")

    delta = payload.get("current_vs_previous_delta")
    lines.append("## What Got Worse")
    lines.append("")
    if isinstance(delta, dict):
        lines.append(
            f"- Comparing current `{delta.get('current_candidate_id', 'n/a')}` vs previous `{delta.get('previous_candidate_id', 'n/a')}`"
        )
        lines.append("")
        lines.append("| Metric | Previous | Current | Delta |")
        lines.append("|---|---:|---:|---:|")
        for metric in delta.get("metrics", []):
            name = str(metric.get("metric", "unknown"))
            previous = metric.get("previous", 0)
            current = metric.get("current", 0)
            delta_value = metric.get("delta", 0)
            if isinstance(delta_value, int) and name == "overclaim_fail_count":
                lines.append(f"| {name} | {previous} | {current} | {delta_value:+d} |")
            else:
                lines.append(f"| {name} | {float(previous):.4f} | {float(current):.4f} | {float(delta_value):+.4f} |")
    else:
        lines.append("- Not enough history to compute current-vs-previous deltas.")
    lines.append("")

    lines.append("## Top 5 Rising Failure Flags")
    lines.append("")
    rising = payload.get("top_rising_failure_flags", [])
    if rising:
        lines.append("| Signal | Previous | Current | Delta |")
        lines.append("|---|---:|---:|---:|")
        for row in rising:
            lines.append(
                "| {signal} | {prev} | {curr} | {delta:+d} |".format(
                    signal=row.get("signal", "unknown"),
                    prev=int(row.get("previous_count", 0)),
                    curr=int(row.get("current_count", 0)),
                    delta=int(row.get("delta", 0)),
                )
            )
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Most Regressed 10 Cases")
    lines.append("")
    regressed = payload.get("most_regressed_cases", [])
    if regressed:
        lines.append("| Case ID | Δ Overall | Δ Relevance | Δ Credibility | Pass/Fail | Snippet |")
        lines.append("|---|---:|---:|---:|---|---|")
        for row in regressed:
            lines.append(
                "| {cid} | {d_overall:+.4f} | {d_rel:+.4f} | {d_cred:+.4f} | {pf} | {snippet} |".format(
                    cid=row.get("id", "unknown"),
                    d_overall=_float(row.get("delta_overall")),
                    d_rel=_float(row.get("delta_relevance")),
                    d_cred=_float(row.get("delta_credibility")),
                    pf=row.get("pass_fail_transition", "n/a"),
                    snippet=str(row.get("snippet", "")).replace("|", "/"),
                )
            )
            rationale = str(row.get("rationale", "")).strip()
            if rationale:
                lines.append(f"  - Rationale: {rationale}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## Recommended Next Prompt Adjustments")
    lines.append("")
    recommendations = payload.get("recommended_prompt_adjustments", [])
    if recommendations:
        for item in recommendations:
            signal = str((item or {}).get("signal", "")).strip() or "quality_signal"
            count = int((item or {}).get("count", 0) or 0)
            action = str((item or {}).get("action", "")).strip()
            if action:
                lines.append(f"- `{signal}` ({count}): {action}")
    else:
        lines.append("- None")
    lines.append("")

    lines.append("## History")
    lines.append("")
    lines.append(
        "| Candidate | Model | Version | Overall | Relevance | Credibility | Overclaim fails | Pass rate | Δ Overall | Δ Relevance | Δ Credibility | Δ Overclaim | Δ Pass rate |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for row in payload.get("rows", []):
        lines.append(
            "| {candidate} | {model} | {version} | {overall:.3f} | {relevance:.3f} | {cred:.3f} | {overclaim:d} | {pass_rate:.3f} | {d_overall:+.3f} | {d_rel:+.3f} | {d_cred:+.3f} | {d_overclaim:+d} | {d_pass:+.3f} |".format(
                candidate=row.get("candidate_id", "unknown"),
                model=str(row.get("judge_model", "unknown")),
                version=str(row.get("judge_model_version", row.get("judge_model", "unknown"))),
                overall=_float(row.get("overall_mean")),
                relevance=_float(row.get("relevance_mean")),
                cred=_float(row.get("credibility_mean")),
                overclaim=int(row.get("overclaim_fail_count", 0)),
                pass_rate=_float(row.get("pass_rate")),
                d_overall=_float(row.get("delta_overall")),
                d_rel=_float(row.get("delta_relevance")),
                d_cred=_float(row.get("delta_credibility")),
                d_overclaim=int(row.get("delta_overclaim_fail_count", 0)),
                d_pass=_float(row.get("delta_pass_rate")),
            )
        )
    if not payload.get("rows"):
        lines.append("| (no data) | n/a | n/a | 0.000 | 0.000 | 0.000 | 0 | 0.000 | +0.000 | +0.000 | +0.000 | +0 | +0.000 |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    root = Path(args.artifact_root)
    if not root.exists():
        raise SystemExit(f"Artifact root not found: {root}")

    rows: list[dict[str, Any]] = []
    for candidate_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        row = _extract_row(candidate_dir, mode=args.mode)
        if row is not None:
            rows.append(row)

    rows = sorted(rows, key=lambda item: str(item.get("generated_at") or ""))[-max(1, args.limit) :]
    _compute_row_deltas(rows)

    delta_block: dict[str, Any] | None = None
    rising_flags: list[dict[str, Any]] = []
    regressed_cases: list[dict[str, Any]] = []
    recommended_prompt_adjustments: list[dict[str, Any]] = []
    if len(rows) >= 2:
        previous = rows[-2]
        current = rows[-1]
        delta_block = _current_vs_previous(current=current, previous=previous)
        rising_flags = _rising_failure_flags(current=current, previous=previous)
        regressed_cases = _most_regressed_cases(current=current, previous=previous)
        recommended_prompt_adjustments = list(current.get("recommended_prompt_adjustments", []))
    elif rows:
        recommended_prompt_adjustments = list(rows[-1].get("recommended_prompt_adjustments", []))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": args.mode,
        "count": len(rows),
        "rows": rows,
        "current_vs_previous_delta": delta_block,
        "top_rising_failure_flags": rising_flags,
        "most_regressed_cases": regressed_cases,
        "recommended_prompt_adjustments": recommended_prompt_adjustments,
    }

    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    out_md.write_text(_to_md(payload), encoding="utf-8")

    print("Judge Trend Report")
    print(f"- Rows: {len(rows)}")
    print(f"- Output JSON: {out_json}")
    print(f"- Output MD: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
