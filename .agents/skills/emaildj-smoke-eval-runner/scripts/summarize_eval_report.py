#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


STAGE_ORDER = [
    "CONTEXT_SYNTHESIS",
    "FIT_REASONING",
    "ANGLE_PICKER",
    "ONE_LINER_COMPRESSOR",
    "EMAIL_GENERATION",
    "EMAIL_QA",
    "EMAIL_REWRITE",
]

STAGE_TO_SELECTOR = {
    "CONTEXT_SYNTHESIS": "a",
    "FIT_REASONING": "b",
    "ANGLE_PICKER": "b0",
    "ONE_LINER_COMPRESSOR": "c0",
    "EMAIL_GENERATION": "c",
    "EMAIL_QA": "d",
    "EMAIL_REWRITE": "e",
}

PROVIDER_MARKERS = (
    "openai_unavailable",
    "openai unavailable",
    "nodename nor servname",
    "timeout",
    "transport",
    "provider unavailable",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize an EmailDJ eval report by root cause.")
    parser.add_argument("report_path", help="Path to an eval report JSON file")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected_dict_json:{path}")
    return data


def _append_unique(items: list[str], value: Any) -> None:
    text = str(value or "").strip()
    if text and text not in items:
        items.append(text)


def _first_failed_stage(result: dict[str, Any]) -> str | None:
    pipeline_error = result.get("pipeline_error")
    pipeline_stage: str | None = None
    if isinstance(pipeline_error, dict):
        stage = str(pipeline_error.get("stage") or "").strip()
        if stage and stage != "VALIDATION":
            return stage
        pipeline_stage = stage or None

    judge_results = result.get("judge_results")
    if isinstance(judge_results, dict):
        for stage in STAGE_ORDER:
            stage_result = judge_results.get(stage)
            if isinstance(stage_result, dict) and stage_result.get("pass") is False:
                return stage
    return pipeline_stage


def _collect_markers(result: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    pipeline_error = result.get("pipeline_error")
    if isinstance(pipeline_error, dict):
        _append_unique(markers, pipeline_error.get("code"))
        _append_unique(markers, pipeline_error.get("message"))

    for item in result.get("hard_fail_criteria") or []:
        _append_unique(markers, item)

    judge_results = result.get("judge_results")
    if isinstance(judge_results, dict):
        for stage in STAGE_ORDER:
            stage_result = judge_results.get(stage)
            if not isinstance(stage_result, dict):
                continue
            for item in stage_result.get("failures") or []:
                _append_unique(markers, item)
            for item in stage_result.get("warnings") or []:
                _append_unique(markers, item)

    return markers


def _classify_bucket(result: dict[str, Any], failed_stage: str | None, markers: list[str]) -> str:
    haystack = " ".join(markers).lower()
    if any(marker in haystack for marker in PROVIDER_MARKERS):
        return "provider_or_transport"
    if failed_stage == "VALIDATION":
        return "bad_validation"
    if failed_stage == "CONTEXT_SYNTHESIS":
        return "bad_brief"
    if failed_stage in {"FIT_REASONING", "ANGLE_PICKER", "ONE_LINER_COMPRESSOR"}:
        return "bad_fit_or_angle"
    if failed_stage == "EMAIL_QA":
        return "bad_validation"
    if failed_stage in {"EMAIL_GENERATION", "EMAIL_REWRITE"}:
        return "bad_generation"
    if result.get("pipeline_ok") is False:
        return "provider_or_transport" if "transport" in haystack else "unknown"
    return "unknown"


def _replay_command(payload_id: str, failed_stage: str | None) -> str | None:
    if not failed_stage:
        return None
    if failed_stage == "CONTEXT_SYNTHESIS":
        return f"cd backend && python -m evals.debug_stage --stage a --payload {payload_id} --raw"
    selector = STAGE_TO_SELECTOR.get(failed_stage)
    if not selector:
        return None
    return f"cd backend && python -m evals.eval_run --payloads {payload_id} --stages {selector} --raw --fail-fast"


def main() -> None:
    args = _parse_args()
    report_path = Path(args.report_path).resolve()
    report = _load_json(report_path)

    payload_results = [item for item in report.get("payload_results") or [] if isinstance(item, dict)]
    bucket_counts: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()
    marker_counts: Counter[str] = Counter()
    failed_payloads: list[dict[str, Any]] = []

    for result in payload_results:
        if result.get("overall_pass") is True:
            continue
        payload_id = str(result.get("payload_id") or "").strip()
        failed_stage = _first_failed_stage(result)
        markers = _collect_markers(result)
        bucket = _classify_bucket(result, failed_stage, markers)

        bucket_counts[bucket] += 1
        if failed_stage:
            stage_counts[failed_stage] += 1
        for marker in markers:
            marker_counts[marker] += 1

        pipeline_error = result.get("pipeline_error") if isinstance(result.get("pipeline_error"), dict) else {}
        failed_payloads.append(
            {
                "payload_id": payload_id,
                "payload_type": str(result.get("payload_type") or "").strip() or None,
                "bucket": bucket,
                "failed_stage": failed_stage,
                "pipeline_error_code": str(pipeline_error.get("code") or "").strip() or None,
                "replay_command": _replay_command(payload_id, failed_stage),
            }
        )

    payload = {
        "report_path": str(report_path),
        "run_id": report.get("run_id"),
        "payload_count": report.get("payload_count"),
        "overall_pass_rate": report.get("overall_pass_rate"),
        "hard_fail_rate": report.get("hard_fail_rate"),
        "stage_pass_rates": report.get("stage_pass_rates"),
        "failure_buckets": dict(sorted(bucket_counts.items())),
        "failures_by_stage": dict(sorted(stage_counts.items())),
        "top_repeated_markers": [
            {"marker": marker, "count": count}
            for marker, count in marker_counts.most_common(10)
        ],
        "failed_payloads": failed_payloads,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
