from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .stage_judge import CRITERIA_BY_STAGE


STAGE_ORDER = [
    "CONTEXT_SYNTHESIS",
    "FIT_REASONING",
    "ANGLE_PICKER",
    "ONE_LINER_COMPRESSOR",
    "EMAIL_GENERATION",
    "EMAIL_QA",
    "EMAIL_REWRITE",
]

PROMPT_FILE_BY_STAGE = {
    "CONTEXT_SYNTHESIS": "backend/app/engine/prompts/stage_a.py",
    "FIT_REASONING": "backend/app/engine/prompts/stage_b.py",
    "ANGLE_PICKER": "backend/app/engine/prompts/stage_b0.py",
    "ONE_LINER_COMPRESSOR": "backend/app/engine/prompts/stage_c0.py",
    "EMAIL_GENERATION": "backend/app/engine/prompts/stage_c.py",
    "EMAIL_QA": "backend/app/engine/prompts/stage_d.py",
    "EMAIL_REWRITE": "backend/app/engine/prompts/stage_e.py",
}

CRITERION_STAGE_INDEX = {
    criterion: stage
    for stage, criteria in CRITERIA_BY_STAGE.items()
    for criterion in criteria
}


def _pct(value: float) -> str:
    return f"{int(round(value * 100.0)):>3d}%"


def _progress_bar(value: float, width: int = 10) -> str:
    clamped = max(0.0, min(1.0, float(value)))
    filled = int(round(clamped * width))
    return "#" * filled + "-" * (width - filled)


def _top_failures(failure_taxonomy: dict[str, dict[str, Any]], top_n: int = 3) -> list[tuple[str, int]]:
    ranked = sorted(
        ((criterion, int(data.get("failures") or 0)) for criterion, data in failure_taxonomy.items()),
        key=lambda item: item[1],
        reverse=True,
    )
    return [item for item in ranked if item[1] > 0][:top_n]


def _recommended_fix_sentence(criterion: str) -> str:
    stage = CRITERION_STAGE_INDEX.get(criterion, "UNKNOWN")
    prompt_file = PROMPT_FILE_BY_STAGE.get(stage, "backend/app/engine/prompts/")
    return f"Review {criterion} rubric alignment in {prompt_file} and corresponding stage validator expectations."


def build_report(
    *,
    run_id: str,
    run_timestamp: str,
    payload_results: list[dict[str, Any]],
    selected_stage_names: list[str],
    regression_vs_golden: dict[str, Any] | None,
) -> dict[str, Any]:
    payload_count = len(payload_results)
    overall_pass_count = sum(1 for item in payload_results if bool(item.get("overall_pass")))
    overall_pass_rate = (overall_pass_count / payload_count) if payload_count else 0.0

    stage_pass_rates: dict[str, float] = {}
    for stage in STAGE_ORDER:
        if stage not in selected_stage_names:
            stage_pass_rates[stage] = 0.0
            continue
        judged = [
            item.get("judge_results", {}).get(stage)
            for item in payload_results
            if isinstance(item.get("judge_results", {}), dict)
        ]
        judged = [entry for entry in judged if isinstance(entry, dict)]
        if not judged:
            stage_pass_rates[stage] = 0.0
            continue
        passed = sum(1 for entry in judged if bool(entry.get("pass")))
        stage_pass_rates[stage] = passed / len(judged)

    all_criteria = [criterion for stage in STAGE_ORDER for criterion in CRITERIA_BY_STAGE.get(stage, [])]
    failure_taxonomy: dict[str, dict[str, Any]] = {
        criterion: {"failures": 0, "payloads": []} for criterion in all_criteria
    }

    hard_fail_count = 0
    for payload in payload_results:
        if bool(payload.get("hard_fail_triggered")):
            hard_fail_count += 1
        payload_id = str(payload.get("payload_id") or "")
        judge_results = payload.get("judge_results") if isinstance(payload.get("judge_results"), dict) else {}
        for stage in STAGE_ORDER:
            stage_result = judge_results.get(stage)
            if not isinstance(stage_result, dict):
                continue
            scores = stage_result.get("scores") if isinstance(stage_result.get("scores"), dict) else {}
            for criterion in CRITERIA_BY_STAGE.get(stage, []):
                if int(scores.get(criterion) or 0) == 0:
                    slot = failure_taxonomy[criterion]
                    slot["failures"] = int(slot["failures"] or 0) + 1
                    if payload_id and payload_id not in slot["payloads"]:
                        slot["payloads"].append(payload_id)

    hard_fail_rate = (hard_fail_count / payload_count) if payload_count else 0.0

    top_failures = _top_failures(failure_taxonomy, top_n=3)
    memo_top_failures = [f"{name} ({count}/{payload_count})" for name, count in top_failures]
    memo_recommended_fixes = [_recommended_fix_sentence(name) for name, _ in top_failures]
    memo_stages_to_prioritize = [stage for stage in STAGE_ORDER if stage in selected_stage_names and stage_pass_rates[stage] < 0.7]

    return {
        "run_id": run_id,
        "run_timestamp": run_timestamp,
        "payload_count": payload_count,
        "overall_pass_rate": overall_pass_rate,
        "stage_pass_rates": stage_pass_rates,
        "hard_fail_rate": hard_fail_rate,
        "failure_taxonomy": failure_taxonomy,
        "payload_results": payload_results,
        "regression_vs_golden": regression_vs_golden,
        "calibration_memo": {
            "top_failures": memo_top_failures,
            "recommended_fixes": memo_recommended_fixes,
            "stages_to_prioritize": memo_stages_to_prioritize,
        },
    }


def write_report_json(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")


def render_stdout_summary(report: dict[str, Any]) -> str:
    payload_count = int(report.get("payload_count") or 0)
    pass_count = sum(1 for item in report.get("payload_results", []) if item.get("overall_pass"))
    fail_count = max(0, payload_count - pass_count)

    lines: list[str] = []
    lines.append("+--------------------------------------------------+")
    lines.append(f"| EmailDJ Eval Run - {report.get('run_id', ''):<30}|")
    lines.append("+--------------------------------------------------+")
    lines.append(f"| Payloads: {payload_count:<3d} | Pass: {pass_count:<3d} | Fail: {fail_count:<3d}           |")
    lines.append(f"| Overall pass rate: {_pct(float(report.get('overall_pass_rate') or 0.0)):<6}                     |")
    lines.append("+--------------------------------------------------+")
    lines.append("| Stage Pass Rates                                 |")

    stage_pass_rates = report.get("stage_pass_rates") if isinstance(report.get("stage_pass_rates"), dict) else {}
    for stage in STAGE_ORDER:
        rate = float(stage_pass_rates.get(stage) or 0.0)
        bar = _progress_bar(rate)
        label = stage[:20].ljust(20)
        lines.append(f"| {label} {bar} {_pct(rate):>4}                |")

    lines.append("+--------------------------------------------------+")
    lines.append("| Top failures                                     |")
    top_failures = _top_failures(report.get("failure_taxonomy") or {}, top_n=3)
    if not top_failures:
        lines.append("| none                                             |")
    else:
        for idx, (criterion, count) in enumerate(top_failures, start=1):
            text = f"{idx}. {criterion} ({count}/{payload_count})"
            lines.append(f"| {text[:48].ljust(48)}|")

    priority = report.get("calibration_memo", {}).get("stages_to_prioritize")
    if isinstance(priority, list) and priority:
        lines.append("+--------------------------------------------------+")
        lines.append(f"| Prioritize: {', '.join(str(item) for item in priority)[:37].ljust(37)}|")

    lines.append("+--------------------------------------------------+")
    return "\n".join(lines)
