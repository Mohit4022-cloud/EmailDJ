from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evals.models import EvalCase, EvalExpected, EvalResult, JudgeSummary, ScorecardSummary


def load_cases(path: Path, *, min_cases: int = 80) -> list[EvalCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Gold set must be a list of test cases.")

    ids: set[str] = set()
    cases: list[EvalCase] = []
    for item in raw:
        case = _parse_case(item)
        if case.id in ids:
            raise ValueError(f"Duplicate case id: {case.id}")
        ids.add(case.id)
        cases.append(case)

    if len(cases) < min_cases:
        raise ValueError(f"Gold set must contain at least {min_cases} cases, found {len(cases)}")

    return cases


def load_smoke_ids(path: Path) -> set[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Smoke ids file must be a list.")
    return {str(item).strip() for item in raw if str(item).strip()}


def _parse_case(item: dict[str, Any]) -> EvalCase:
    required_top = (
        "id",
        "tags",
        "prospect",
        "seller",
        "offer_lock",
        "cta_lock",
        "cta_type",
        "style_profile",
        "research_text",
        "other_products",
        "expected",
    )
    for key in required_top:
        if key not in item:
            raise ValueError(f"Case missing required key '{key}': {item}")

    expected_raw = item["expected"]
    if not isinstance(expected_raw, dict):
        raise ValueError(f"Case expected block invalid for {item.get('id')}")

    expected = EvalExpected(
        must_include=[str(x) for x in expected_raw.get("must_include", []) if str(x).strip()],
        must_not_include=[str(x) for x in expected_raw.get("must_not_include", []) if str(x).strip()],
        greeting_first_name=str(expected_raw.get("greeting_first_name", "")).strip(),
    )

    style = item["style_profile"]
    if not isinstance(style, dict):
        raise ValueError(f"style_profile must be object for {item.get('id')}")

    return EvalCase(
        id=str(item["id"]).strip(),
        tags=[str(x).strip() for x in item.get("tags", []) if str(x).strip()],
        prospect={k: str(v) for k, v in item.get("prospect", {}).items()},
        seller={k: str(v) for k, v in item.get("seller", {}).items()},
        offer_lock=str(item["offer_lock"]).strip(),
        cta_lock=str(item["cta_lock"]).strip(),
        cta_type=(str(item["cta_type"]).strip() or None) if item.get("cta_type") is not None else None,
        style_profile={
            "formality": float(style.get("formality", 0.0)),
            "orientation": float(style.get("orientation", 0.0)),
            "length": float(style.get("length", 0.0)),
            "assertiveness": float(style.get("assertiveness", 0.0)),
        },
        research_text=str(item["research_text"]),
        other_products=[str(x).strip() for x in item.get("other_products", []) if str(x).strip()],
        expected=expected,
        approved_proof_points=[str(x).strip() for x in item.get("approved_proof_points", []) if str(x).strip()],
    )


def write_reports(
    report_dir: Path,
    *,
    mode: str,
    selection_mode: str,
    selected_tags: list[str],
    summary: ScorecardSummary,
    results: list[EvalResult],
    top_failures: list[dict[str, Any]],
    judge_summary: JudgeSummary | None = None,
    top_quality_failures: list[dict[str, Any]] | None = None,
    recommended_prompt_adjustments: list[dict[str, Any]] | None = None,
) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    history_dir = report_dir / "history"
    history_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y%m%dT%H%M%SZ")

    payload: dict[str, Any] = {
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "mode": mode,
        "selection": {
            "selection_mode": selection_mode,
            "tags": selected_tags,
        },
        "summary": summary.to_dict(),
        "top_recurring_failures": top_failures,
        "results": [result.to_dict() for result in results],
    }
    if judge_summary is not None:
        payload["judge"] = {
            "summary": judge_summary.to_dict(),
            "top_recurring_quality_failures": top_quality_failures or [],
            "recommended_prompt_adjustments": recommended_prompt_adjustments or [],
        }

    latest_json = report_dir / "latest.json"
    latest_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    (history_dir / f"{ts}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    latest_md = report_dir / "latest.md"
    latest_md.write_text(_to_markdown(payload), encoding="utf-8")
    (history_dir / f"{ts}.md").write_text(_to_markdown(payload), encoding="utf-8")

    return latest_json, latest_md


def _to_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines: list[str] = []
    lines.append("# Lock Compliance Scorecard")
    lines.append("")
    lines.append(f"- Generated at: `{payload['generated_at']}`")
    lines.append(f"- Mode: `{payload['mode']}`")
    lines.append(f"- Selection: `{payload['selection']['selection_mode']}`")
    tags = payload["selection"].get("tags") or []
    lines.append(f"- Tags: `{', '.join(tags) if tags else '(none)'}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|---|---:|")
    lines.append(f"| Total cases | {summary['total_cases']} |")
    lines.append(f"| Passed | {summary['passed_cases']} |")
    lines.append(f"| Failed | {summary['failed_cases']} |")
    lines.append(f"| Pass rate | {summary['pass_rate']:.2%} |")
    lines.append(f"| Total violations | {summary['violation_count']} |")
    lines.append("")

    lines.append("## Failure Counts")
    lines.append("")
    lines.append("| Violation code | Count |")
    lines.append("|---|---:|")
    for code, count in sorted(summary["failure_count_by_code"].items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {code} | {count} |")
    lines.append("")

    lines.append("## Top Recurring Failures")
    lines.append("")
    for row in payload.get("top_recurring_failures", []):
        lines.append(f"- `{row['code']}` x{row['count']} (examples: {', '.join(row.get('cases', [])[:5])})")
    if not payload.get("top_recurring_failures"):
        lines.append("- None")
    lines.append("")

    judge = payload.get("judge")
    if judge:
        judge_summary = judge.get("summary", {})
        lines.append("## Quality Judge Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|---|---:|")
        lines.append(f"| Enabled | {judge_summary.get('enabled', False)} |")
        lines.append(f"| Model | `{judge_summary.get('model', 'unknown')}` |")
        lines.append(f"| Model version | `{judge_summary.get('model_version', judge_summary.get('model', 'unknown'))}` |")
        lines.append(f"| Mode | `{judge_summary.get('mode', 'unknown')}` |")
        lines.append(f"| Schema version | `{judge_summary.get('schema_version', 'unknown')}` |")
        lines.append(f"| Evaluated cases | {judge_summary.get('evaluated_cases', 0)} |")
        lines.append(f"| Skipped (hard fail) | {judge_summary.get('skipped_cases', 0)} |")
        lines.append(f"| Passed | {judge_summary.get('passed_cases', 0)} |")
        lines.append(f"| Failed | {judge_summary.get('failed_cases', 0)} |")
        lines.append(f"| Pass rate | {judge_summary.get('pass_rate', 0):.2%} |")
        lines.append(f"| Mean overall | {judge_summary.get('mean_overall', 0):.2f} |")
        lines.append(f"| Mean relevance | {judge_summary.get('mean_relevance', 0):.2f} |")
        lines.append(f"| Mean credibility | {judge_summary.get('mean_credibility', 0):.2f} |")
        lines.append(f"| Overclaim fail count | {judge_summary.get('overclaim_fail_count', 0)} |")
        lines.append(f"| Threshold overall | {judge_summary.get('threshold_overall', 0):.2f} |")
        lines.append(f"| Threshold credibility | {judge_summary.get('threshold_credibility', 0):.2f} |")
        lines.append(f"| Cache hits | {judge_summary.get('cache_hits', 0)} / {judge_summary.get('cache_lookups', 0)} |")
        lines.append(f"| Cache hit rate | {judge_summary.get('cache_hit_rate', 0):.2%} |")
        lines.append(f"| Prompt contract hash | `{judge_summary.get('prompt_contract_hash', '')}` |")
        if judge_summary.get("calibration_examples", 0):
            lines.append(f"| Calibration examples | {judge_summary.get('calibration_examples', 0)} |")
            agreement = judge_summary.get("calibration_pass_fail_agreement")
            rank_corr = judge_summary.get("calibration_score_rank_correlation")
            lines.append(f"| Calibration pass/fail agreement | {agreement if agreement is not None else 'n/a'} |")
            lines.append(f"| Calibration rank correlation | {rank_corr if rank_corr is not None else 'n/a'} |")
        lines.append("")
        lines.append("## Top Recurring Quality Failures")
        lines.append("")
        top_quality = judge.get("top_recurring_quality_failures", [])
        if top_quality:
            for row in top_quality:
                lines.append(f"- `{row['flag']}` x{row['count']}")
        else:
            lines.append("- None")
        lines.append("")
        lines.append("## Recommended Next Prompt Adjustments")
        lines.append("")
        recommendations = judge.get("recommended_prompt_adjustments", [])
        if recommendations:
            for row in recommendations:
                action = str((row or {}).get("action", "")).strip()
                signal = str((row or {}).get("signal", "")).strip() or "quality_signal"
                count = int((row or {}).get("count", 0) or 0)
                if action:
                    lines.append(f"- `{signal}` ({count}): {action}")
        else:
            lines.append("- None")
        lines.append("")

    lines.append("## Per-test Results")
    lines.append("")
    for result in payload["results"]:
        state = "PASS" if result["passed"] else "FAIL"
        lines.append(f"### {result['id']} - {state}")
        lines.append(f"- Duration: `{result['duration_ms']}ms`")
        lines.append(f"- Tags: `{', '.join(result.get('tags', []))}`")
        if result.get("error"):
            lines.append(f"- Error: `{result['error']}`")
        if result.get("violations"):
            for v in result["violations"]:
                snippet = v.get("snippet") or ""
                lines.append(f"- `{v['code']}`: {v['reason']}" + (f" | snippet: `{snippet}`" if snippet else ""))
        judge_result = result.get("judge") or {}
        if judge_result:
            lines.append(f"- Judge status: `{judge_result.get('status', 'disabled')}`")
            if judge_result.get("status") == "scored":
                lines.append(f"- Judge pass/fail: `{judge_result.get('pass_fail', 'fail')}`")
                lines.append(f"- Judge overall: `{judge_result.get('overall', 0):.2f}`")
                flags = judge_result.get("flags") or []
                lines.append(f"- Judge flags: `{', '.join(flags) if flags else '(none)'}`")
                for bullet in (judge_result.get("rationale_bullets") or [])[:3]:
                    lines.append(f"- Judge rationale: {bullet}")
                for action in (judge_result.get("repair_actions") or [])[:3]:
                    if isinstance(action, dict):
                        tag = action.get("tag", "")
                        step = action.get("action", "")
                        if tag and step:
                            lines.append(f"- Repair {tag}: {step}")
            elif judge_result.get("status") == "error":
                lines.append(f"- Judge error: `{judge_result.get('error', 'unknown')}`")
        feedback = result.get("actionable_feedback") or []
        for item in feedback[:4]:
            lines.append(f"- Action: {item}")
        lines.append("")

    return "\n".join(lines).strip() + "\n"
