from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.io import load_cases
from evals.judge.cache import JudgeCache
from evals.judge.client import JudgeClient, JudgeRuntime


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pairwise judge comparisons across two eval reports.")
    parser.add_argument("--a-report", required=True, help="Path to report JSON for candidate A.")
    parser.add_argument("--b-report", required=True, help="Path to report JSON for candidate B.")
    parser.add_argument("--dataset", default="evals/gold_set.full.json")
    parser.add_argument("--report-dir", default="reports/judge")
    parser.add_argument("--judge-mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--judge-model", default="gpt-4.1-mini")
    parser.add_argument("--judge-model-version", default=(os.environ.get("EMAILDJ_JUDGE_MODEL_VERSION", "").strip()))
    parser.add_argument("--judge-sample-count", type=int, default=1)
    parser.add_argument("--judge-cache-dir", default="reports/judge/cache")
    parser.add_argument("--label-a", default="A")
    parser.add_argument("--label-b", default="B")
    args = parser.parse_args()
    args.judge_model_version = (
        str(args.judge_model_version).strip()
        or args.judge_model.strip()
        or "gpt-4.1-mini"
    )
    return args


def _load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid report at {path}")
    return data


def _extract_draft(item: dict[str, Any]) -> str:
    draft = str(item.get("draft", "")).strip()
    if draft:
        return draft
    subject = str(item.get("subject", "")).strip()
    body = str(item.get("body", "")).strip()
    return f"Subject: {subject}\nBody:\n{body}".strip()


def _to_markdown(payload: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# Judge Pairwise Report")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Judge model: `{payload['judge']['model']}`")
    lines.append(f"- Judge model version: `{payload['judge'].get('model_version', payload['judge']['model'])}`")
    lines.append(f"- Judge mode: `{payload['judge']['mode']}`")
    lines.append(f"- Candidate A: `{payload['candidate_a']}`")
    lines.append(f"- Candidate B: `{payload['candidate_b']}`")
    lines.append("")
    summary = payload["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Cases compared: `{summary['cases_compared']}`")
    lines.append(f"- A wins: `{summary['wins_a']}`")
    lines.append(f"- B wins: `{summary['wins_b']}`")
    lines.append(f"- Ties: `{summary['ties']}`")
    lines.append("")
    lines.append("## Per-case")
    lines.append("")
    for row in payload["results"]:
        lines.append(f"### {row['id']} - winner: {row['winner']}")
        lines.append(f"- Confidence: `{row['confidence']}`")
        flags = row.get("flags", [])
        lines.append(f"- Flags: `{', '.join(flags) if flags else '(none)'}`")
        for bullet in row.get("rationale_bullets", [])[:3]:
            lines.append(f"- Rationale: {bullet}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    args = _parse_args()
    report_a = _load_report(Path(args.a_report))
    report_b = _load_report(Path(args.b_report))

    cases = load_cases(Path(args.dataset), min_cases=1)
    by_case = {case.id: case for case in cases}

    by_a = {str(item.get("id")): item for item in report_a.get("results", []) if isinstance(item, dict)}
    by_b = {str(item.get("id")): item for item in report_b.get("results", []) if isinstance(item, dict)}
    common_ids = sorted(set(by_a.keys()) & set(by_b.keys()) & set(by_case.keys()))

    cache = JudgeCache(Path(args.judge_cache_dir))
    client = JudgeClient(
        cache=cache,
        runtime=JudgeRuntime(
            mode=args.judge_mode,
            model=args.judge_model,
            timeout_seconds=float(30),
            sample_count=max(1, int(args.judge_sample_count)),
            model_version=args.judge_model_version,
            secondary_model=None,
        ),
    )

    rows: list[dict[str, Any]] = []
    wins_a = 0
    wins_b = 0
    ties = 0

    for case_id in common_ids:
        item_a = by_a[case_id]
        item_b = by_b[case_id]
        lock_a = bool(item_a.get("passed", False))
        lock_b = bool(item_b.get("passed", False))
        if not lock_a or not lock_b:
            rows.append(
                {
                    "id": case_id,
                    "winner": "tie",
                    "confidence": 0.0,
                    "flags": ["auto_fail_policy_or_compliance_risk"],
                    "rationale_bullets": ["Skipped pairwise comparison because one candidate failed hard lock checks."],
                }
            )
            ties += 1
            continue

        pair = client.evaluate_pairwise(
            case=by_case[case_id],
            draft_a=_extract_draft(item_a),
            draft_b=_extract_draft(item_b),
            eval_mode="pairwise",
            candidate_id=f"{args.label_a}_vs_{args.label_b}",
        )
        winner = pair.get("winner", "tie")
        if winner == "A":
            wins_a += 1
            final_winner = args.label_a
        elif winner == "B":
            wins_b += 1
            final_winner = args.label_b
        else:
            ties += 1
            final_winner = "tie"
        rows.append(
            {
                "id": case_id,
                "winner": final_winner,
                "confidence": pair.get("confidence", 0.0),
                "order_swapped": bool(pair.get("order_swapped", False)),
                "flags": pair.get("flags", []),
                "rationale_bullets": pair.get("rationale_bullets", []),
            }
        )

    now = datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "candidate_a": args.label_a,
        "candidate_b": args.label_b,
        "judge": {
            "model": args.judge_model,
            "model_version": args.judge_model_version,
            "mode": args.judge_mode,
        },
        "summary": {
            "cases_compared": len(rows),
            "wins_a": wins_a,
            "wins_b": wins_b,
            "ties": ties,
        },
        "results": rows,
    }

    out_dir = Path(args.report_dir)
    history_dir = out_dir / "history"
    out_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)
    ts = now.strftime("%Y%m%dT%H%M%SZ")

    latest_json = out_dir / "pairwise_latest.json"
    latest_md = out_dir / "pairwise_latest.md"
    latest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest_md.write_text(_to_markdown(payload), encoding="utf-8")
    (history_dir / f"pairwise_{ts}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (history_dir / f"pairwise_{ts}.md").write_text(_to_markdown(payload), encoding="utf-8")

    print("Judge Pairwise")
    print(f"- Cases compared: {len(rows)}")
    print(f"- {args.label_a} wins: {wins_a}")
    print(f"- {args.label_b} wins: {wins_b}")
    print(f"- Ties: {ties}")
    print(f"- Report JSON: {latest_json}")
    print(f"- Report MD: {latest_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
