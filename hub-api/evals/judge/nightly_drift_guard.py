from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Guard judge threshold gating when model/version drift occurs.")
    parser.add_argument("--current-calibration", default="reports/judge/calibration/latest.json")
    parser.add_argument("--previous-metadata", default="reports/judge/previous_nightly_metadata.json")
    parser.add_argument("--out", default="reports/judge/drift_guard/latest.json")
    parser.add_argument("--out-metadata", default="reports/judge/nightly_metadata.json")
    parser.add_argument("--allow-drift-override", action="store_true")
    parser.add_argument("--allow-failures", action="store_true")
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON file: {path}")
    return data


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _thresholds(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("recommended_thresholds") or {}
    return {
        "overall": _float(raw.get("overall"), 0.0),
        "credibility": _float(raw.get("credibility"), 0.0),
    }


def main() -> int:
    args = _parse_args()
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    current_report = _load_json(Path(args.current_calibration))
    previous_path = Path(args.previous_metadata)
    previous_payload = _load_json(previous_path) if previous_path.exists() else None

    current = {
        "judge_model": str(current_report.get("judge_model", "")).strip() or "unknown",
        "judge_model_version": str(
            current_report.get("judge_model_version", current_report.get("judge_model", ""))
        ).strip()
        or "unknown",
        "recommended_thresholds": _thresholds(current_report),
        "generated_at": str(current_report.get("generated_at", "")).strip() or now,
    }

    previous = None
    if isinstance(previous_payload, dict):
        previous = {
            "judge_model": str(previous_payload.get("judge_model", "")).strip() or "unknown",
            "judge_model_version": str(previous_payload.get("judge_model_version", "")).strip()
            or str(previous_payload.get("judge_model", "")).strip()
            or "unknown",
            "recommended_thresholds": _thresholds(previous_payload),
            "generated_at": str(previous_payload.get("generated_at", "")).strip() or "",
        }

    drift_detected = False
    if previous is not None:
        drift_detected = (current["judge_model"], current["judge_model_version"]) != (
            previous["judge_model"],
            previous["judge_model_version"],
        )

    delta = None
    if previous is not None:
        delta = {
            "overall": round(
                _float(current["recommended_thresholds"].get("overall"))
                - _float(previous["recommended_thresholds"].get("overall")),
                4,
            ),
            "credibility": round(
                _float(current["recommended_thresholds"].get("credibility"))
                - _float(previous["recommended_thresholds"].get("credibility")),
                4,
            ),
        }

    blocked = bool(drift_detected and not args.allow_drift_override)
    report = {
        "generated_at": now,
        "drift_detected": drift_detected,
        "override_used": bool(args.allow_drift_override),
        "gate_status": "blocked" if blocked else "allowed",
        "current": current,
        "previous": previous,
        "threshold_delta": delta,
        "message": (
            "Judge model/version changed. Manual override is required before enabling thresholds as a gate."
            if blocked
            else "Judge drift guard passed."
        ),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    metadata = {
        "generated_at": now,
        "judge_model": current["judge_model"],
        "judge_model_version": current["judge_model_version"],
        "recommended_thresholds": current["recommended_thresholds"],
        "source_calibration_report": str(Path(args.current_calibration)),
    }
    metadata_path = Path(args.out_metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print("Judge Drift Guard")
    print(f"- Drift detected: {drift_detected}")
    print(f"- Override used: {bool(args.allow_drift_override)}")
    if previous is not None:
        print(
            "- Threshold delta: overall={:+.4f}, credibility={:+.4f}".format(
                _float((delta or {}).get("overall")),
                _float((delta or {}).get("credibility")),
            )
        )
    else:
        print("- Threshold delta: n/a (no previous nightly metadata)")
    print(f"- Gate status: {report['gate_status']}")
    print(f"- Report: {out_path}")
    print(f"- Metadata: {metadata_path}")

    if args.allow_failures:
        return 0
    return 1 if blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
