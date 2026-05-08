#!/usr/bin/env python3
"""Merge per-flow HTTP smoke summaries into one launch-check artifact."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"summary_missing:{path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"summary_invalid_json:{path}:{exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"summary_not_object:{path}")
    return payload


def _int_value(payload: dict[str, Any], key: str) -> int:
    try:
        return int(payload.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _float_value(payload: dict[str, Any], key: str) -> float:
    try:
        return float(payload.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _merge_count_map(target: Counter, value: Any) -> None:
    for key, count in dict(value or {}).items():
        try:
            target[str(key)] += int(count or 0)
        except (TypeError, ValueError):
            continue


def _merge_pass_fail_map(target: dict[str, dict[str, int]], value: Any) -> None:
    for key, counts in dict(value or {}).items():
        row = target[str(key)]
        for field in ("total", "pass", "fail"):
            try:
                row[field] += int((counts or {}).get(field, 0) or 0)
            except (TypeError, ValueError, AttributeError):
                continue


def _merge_total_pass_map(target: dict[str, dict[str, int]], value: Any) -> None:
    for key, counts in dict(value or {}).items():
        row = target[str(key)]
        for field in ("total", "pass"):
            try:
                row[field] += int((counts or {}).get(field, 0) or 0)
            except (TypeError, ValueError, AttributeError):
                continue


def _launch_gate(provider_counts: Counter, route_counts: dict[str, dict[str, int]], *, failed: int, errors: int) -> dict[str, str]:
    shim_count = provider_counts.get("provider_stub", 0) + provider_counts.get("provider_shim", 0)
    external_count = provider_counts.get("external_provider", 0)
    remix_total = route_counts.get("remix", {}).get("total", 0)
    remix_fail = route_counts.get("remix", {}).get("fail", 0)
    return {
        "backend_green": "not_run",
        "harness_green": "not_run",
        "shim_green": "green" if shim_count > 0 and failed == 0 and errors == 0 else "red" if shim_count > 0 else "not_run",
        "provider_green": "green" if external_count > 0 and failed == 0 and errors == 0 else "red" if external_count > 0 else "not_run",
        "remix_green": "green" if remix_total > 0 and remix_fail == 0 and errors == 0 else "red" if remix_total > 0 else "not_run",
    }


def merge_summaries(summary_paths: list[Path]) -> dict[str, Any]:
    if not summary_paths:
        raise RuntimeError("no_summaries_to_merge")

    payloads = [_load_summary(path) for path in summary_paths]
    total = sum(_int_value(payload, "total") for payload in payloads)
    passed = sum(_int_value(payload, "pass") for payload in payloads)
    failed = sum(_int_value(payload, "fail") for payload in payloads)
    errors = sum(_int_value(payload, "errors") for payload in payloads)

    provider_counts: Counter = Counter()
    violation_counts: Counter = Counter()
    fail_tag_counts: Counter = Counter()
    route_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0})
    preset_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0, "fail": 0})
    persona_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0})
    preset_breakdown: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "pass": 0})
    violation_by_route: dict[str, Counter] = defaultdict(Counter)
    violation_by_preset: dict[str, Counter] = defaultdict(Counter)
    top_worst: list[dict[str, Any]] = []

    required_field_miss_count = 0
    under_length_miss_count = 0
    claims_policy_intervention_count = 0
    elapsed_seconds = 0.0
    source_summaries: list[dict[str, Any]] = []
    modes: list[str] = []

    for path, payload in zip(summary_paths, payloads):
        mode = str(payload.get("mode") or "unknown")
        if mode not in modes:
            modes.append(mode)
        elapsed_seconds += _float_value(payload, "elapsed_seconds")
        required_field_miss_count += _int_value(payload, "required_field_miss_count")
        under_length_miss_count += _int_value(payload, "under_length_miss_count")
        claims_policy_intervention_count += _int_value(payload, "claims_policy_intervention_count")
        _merge_count_map(provider_counts, payload.get("provider_source_counts"))
        _merge_count_map(violation_counts, payload.get("top_violation_codes"))
        _merge_count_map(fail_tag_counts, payload.get("fail_tag_counts"))
        _merge_pass_fail_map(route_counts, payload.get("route_pass_fail_counts"))
        _merge_pass_fail_map(preset_counts, payload.get("preset_pass_fail_counts"))
        _merge_total_pass_map(persona_counts, payload.get("breakdown_by_persona_type"))
        _merge_total_pass_map(preset_breakdown, payload.get("breakdown_by_preset"))
        for route, counts in dict(payload.get("top_violation_codes_by_route") or {}).items():
            _merge_count_map(violation_by_route[str(route)], counts)
        for preset, counts in dict(payload.get("top_violation_codes_by_preset") or {}).items():
            _merge_count_map(violation_by_preset[str(preset)], counts)
        top_worst.extend(list(payload.get("top_10_worst") or []))
        source_summaries.append(
            {
                "path": str(path),
                "run_id": payload.get("run_id"),
                "mode": payload.get("mode"),
                "total": payload.get("total"),
                "pass": payload.get("pass"),
                "fail": payload.get("fail"),
                "errors": payload.get("errors"),
            }
        )

    return {
        "run_id": f"merged_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "mode": "+".join(modes),
        "timestamp_utc": _utc_now_text(),
        "elapsed_seconds": round(elapsed_seconds, 1),
        "total": total,
        "pass": passed,
        "fail": failed,
        "errors": errors,
        "pass_rate_pct": round(passed / total * 100, 1) if total else 0.0,
        "provider_source_counts": dict(provider_counts),
        "route_pass_fail_counts": dict(route_counts),
        "preset_pass_fail_counts": dict(preset_counts),
        "top_violation_codes": dict(violation_counts.most_common(10)),
        "top_violation_codes_by_route": {route: dict(counter.most_common(5)) for route, counter in violation_by_route.items()},
        "top_violation_codes_by_preset": {preset: dict(counter.most_common(5)) for preset, counter in violation_by_preset.items()},
        "required_field_miss_count": required_field_miss_count,
        "required_field_miss_rate": round(required_field_miss_count / total, 4) if total else 0.0,
        "under_length_miss_count": under_length_miss_count,
        "under_length_miss_rate": round(under_length_miss_count / total, 4) if total else 0.0,
        "claims_policy_intervention_count": claims_policy_intervention_count,
        "preview_generate_parity_status": "not_run",
        "launch_gates": _launch_gate(provider_counts, route_counts, failed=failed, errors=errors),
        "fail_tag_counts": dict(fail_tag_counts.most_common()),
        "top_10_worst": top_worst[:10],
        "breakdown_by_persona_type": dict(persona_counts),
        "breakdown_by_preset": dict(preset_breakdown),
        "source_summaries": source_summaries,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge HTTP smoke summary.json files into one launch-check summary.")
    parser.add_argument("--out", required=True, help="Output summary.json path.")
    parser.add_argument("summaries", nargs="+", help="Input summary.json paths.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        merged = merge_summaries([Path(path) for path in args.summaries])
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "total": merged["total"], "pass": merged["pass"], "fail": merged["fail"], "errors": merged["errors"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
