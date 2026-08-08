from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


MIN_ONE_LINER_PASS_RATE = 0.6


def _payload_ids_with_hard_fails(report: dict[str, Any]) -> list[str]:
    return [
        str(item.get("payload_id") or "")
        for item in report.get("payload_results", [])
        if isinstance(item, dict) and item.get("hard_fail_triggered")
    ]


def _regressed_payload_ids(report: dict[str, Any]) -> list[str]:
    regression = report.get("regression_vs_golden")
    if not isinstance(regression, dict):
        return []
    return [str(item) for item in regression.get("regressed") or []]


def evaluate_ci_gate(
    report: dict[str, Any],
    *,
    report_path: str,
    golden_present: bool,
) -> dict[str, Any]:
    hard_fail_payloads = [payload_id for payload_id in _payload_ids_with_hard_fails(report) if payload_id]
    regressed = _regressed_payload_ids(report)
    c0_rate = float((report.get("stage_pass_rates") or {}).get("ONE_LINER_COMPRESSOR") or 0.0)

    failures: list[str] = []
    warnings: list[str] = []
    if regressed:
        failures.append("regression_vs_golden detected")
    if golden_present and hard_fail_payloads:
        failures.append("hard_fail_triggered on emaildj payloads")
    if not golden_present and hard_fail_payloads:
        warnings.append("hard_fail_triggered without golden baseline; advisory only")
    if golden_present and c0_rate < MIN_ONE_LINER_PASS_RATE:
        failures.append("ONE_LINER_COMPRESSOR pass rate below 0.6")
    if not golden_present and c0_rate < MIN_ONE_LINER_PASS_RATE:
        warnings.append("ONE_LINER_COMPRESSOR pass rate below 0.6 without golden baseline; advisory only")

    return {
        "report_path": report_path,
        "gate_mode": "golden_regression" if golden_present else "advisory_no_golden",
        "payload_count": int(report.get("payload_count") or 0),
        "overall_pass_rate": float(report.get("overall_pass_rate") or 0.0),
        "one_liner_compressor_pass_rate": c0_rate,
        "hard_fail_payloads": hard_fail_payloads,
        "regressed_payloads": regressed,
        "warnings": warnings,
        "failures": failures,
        "passed": not failures,
    }


def render_summary(result: dict[str, Any]) -> str:
    hard_fail_payloads = result.get("hard_fail_payloads") or []
    regressed = result.get("regressed_payloads") or []
    warnings = result.get("warnings") or []
    failures = result.get("failures") or []
    lines = [
        f"Report: {result.get('report_path')}",
        f"Gate mode: {result.get('gate_mode')}",
        f"Payload count: {result.get('payload_count', 0)}",
        f"Overall pass rate: {float(result.get('overall_pass_rate') or 0.0):.2%}",
        f"ONE_LINER_COMPRESSOR pass rate: {float(result.get('one_liner_compressor_pass_rate') or 0.0):.2%}",
        f"Hard-fail payloads: {', '.join(hard_fail_payloads) if hard_fail_payloads else 'none'}",
        f"Regressed payloads: {', '.join(regressed) if regressed else 'none'}",
    ]
    if warnings:
        lines.append("Warnings:")
        lines.extend(f"- {item}" for item in warnings)
    if failures:
        lines.append("")
        lines.append("Blocking conditions:")
        lines.extend(f"- {item}" for item in failures)
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the legacy EmailDJ CI eval gate.")
    parser.add_argument("report", help="Path to the eval report JSON.")
    parser.add_argument("--summary", default="", help="Optional summary text output path.")
    parser.add_argument("--golden-present", action="store_true", help="Treat hard-fails as blocking golden evidence.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report_path = Path(args.report)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    result = evaluate_ci_gate(report, report_path=str(report_path), golden_present=bool(args.golden_present))
    summary = render_summary(result)
    print(summary)
    if args.summary:
        Path(args.summary).write_text(summary, encoding="utf-8")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
