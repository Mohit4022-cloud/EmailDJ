from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
            meta_raw = _load_json(meta_path)
            if isinstance(meta_raw, dict):
                meta = meta_raw
        except Exception:
            meta = {}
    return {
        "candidate_id": candidate_dir.name,
        "artifact": str(report_path),
        "generated_at": report.get("generated_at"),
        "judge_model": summary.get("model"),
        "judge_mode": summary.get("mode"),
        "prompt_contract_hash": summary.get("prompt_contract_hash"),
        "overall_mean": float(summary.get("mean_overall", 0.0)),
        "credibility_mean": float(summary.get("mean_credibility", 0.0)),
        "pass_rate": float(summary.get("pass_rate", 0.0)),
        "evaluated_cases": int(summary.get("evaluated_cases", 0)),
        "meta_generated_at": meta.get("generated_at"),
    }


def _to_md(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Judge Trend Report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Mode: `{payload['mode']}`")
    lines.append(f"- Samples: `{payload['count']}`")
    lines.append("")
    lines.append("| Candidate | Overall | Credibility | Pass rate | Δ Overall | Δ Credibility | Δ Pass rate |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for row in payload.get("rows", []):
        lines.append(
            "| {candidate} | {overall:.3f} | {cred:.3f} | {pass_rate:.3f} | {d_overall:+.3f} | {d_cred:+.3f} | {d_pass:+.3f} |".format(
                candidate=row.get("candidate_id", "unknown"),
                overall=float(row.get("overall_mean", 0.0)),
                cred=float(row.get("credibility_mean", 0.0)),
                pass_rate=float(row.get("pass_rate", 0.0)),
                d_overall=float(row.get("delta_overall", 0.0)),
                d_cred=float(row.get("delta_credibility", 0.0)),
                d_pass=float(row.get("delta_pass_rate", 0.0)),
            )
        )
    if not payload.get("rows"):
        lines.append("| (no data) | 0.000 | 0.000 | 0.000 | +0.000 | +0.000 | +0.000 |")
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

    prev: dict[str, Any] | None = None
    for row in rows:
        if prev is None:
            row["delta_overall"] = 0.0
            row["delta_credibility"] = 0.0
            row["delta_pass_rate"] = 0.0
        else:
            row["delta_overall"] = round(float(row["overall_mean"]) - float(prev["overall_mean"]), 4)
            row["delta_credibility"] = round(float(row["credibility_mean"]) - float(prev["credibility_mean"]), 4)
            row["delta_pass_rate"] = round(float(row["pass_rate"]) - float(prev["pass_rate"]), 4)
        prev = row

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "mode": args.mode,
        "count": len(rows),
        "rows": rows,
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
