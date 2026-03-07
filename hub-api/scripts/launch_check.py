#!/usr/bin/env python3
"""Compute launch-readiness from hub-api verification artifacts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from email_generation.runtime_policies import launch_mode as runtime_launch_mode


DEFAULT_MAX_AGE_HOURS = 72


@dataclass
class ArtifactStatus:
    path: str | None
    payload: dict[str, Any] | None
    timestamp: datetime | None
    stale: bool
    malformed: bool
    missing: bool
    error: str | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute EmailDJ launch readiness.")
    parser.add_argument("--from-artifacts", action="store_true", help="Read existing artifacts only.")
    parser.add_argument(
        "--localhost-smoke-summary",
        default="",
        help="Optional path to a localhost smoke summary.json artifact to include.",
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Artifact freshness threshold in hours (default: {DEFAULT_MAX_AGE_HOURS}).",
    )
    return parser.parse_args()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_to_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _artifact_timestamp(payload: dict[str, Any]) -> datetime | None:
    for key in ("generated_at", "captured_at_utc", "timestamp_utc"):
        parsed = _parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _artifact_status(path: Path, *, max_age: timedelta) -> ArtifactStatus:
    if not path.exists():
        return ArtifactStatus(path=str(path), payload=None, timestamp=None, stale=False, malformed=False, missing=True)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ArtifactStatus(
            path=str(path),
            payload=None,
            timestamp=None,
            stale=False,
            malformed=True,
            missing=False,
            error=f"unreadable_json:{exc}",
        )
    if not isinstance(payload, dict):
        return ArtifactStatus(
            path=str(path),
            payload=None,
            timestamp=None,
            stale=False,
            malformed=True,
            missing=False,
            error="payload_not_object",
        )
    timestamp = _artifact_timestamp(payload)
    if timestamp is None:
        return ArtifactStatus(
            path=str(path),
            payload=payload,
            timestamp=None,
            stale=False,
            malformed=True,
            missing=False,
            error="missing_timestamp",
        )
    stale = (_utc_now() - timestamp) > max_age
    return ArtifactStatus(
        path=str(path),
        payload=payload,
        timestamp=timestamp,
        stale=stale,
        malformed=False,
        missing=False,
    )


def _latest_json(
    directories: list[Path],
    *,
    max_age: timedelta,
    predicate: Callable[[dict[str, Any]], bool],
) -> ArtifactStatus:
    candidates: list[Path] = []
    for directory in directories:
        if not directory.exists():
            continue
        candidates.extend(sorted(directory.glob("**/summary.json")))
    best: ArtifactStatus | None = None
    for path in candidates:
        status = _artifact_status(path, max_age=max_age)
        if status.payload is None or status.malformed or status.missing:
            continue
        if not predicate(status.payload):
            continue
        if best is None:
            best = status
            continue
        if (status.timestamp or datetime.min.replace(tzinfo=timezone.utc)) > (best.timestamp or datetime.min.replace(tzinfo=timezone.utc)):
            best = status
    return best or ArtifactStatus(path=None, payload=None, timestamp=None, stale=False, malformed=False, missing=True)


def _required_provider_env() -> tuple[str, str]:
    provider = (os.environ.get("EMAILDJ_REAL_PROVIDER") or "openai").strip().lower() or "openai"
    key_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider, "OPENAI_API_KEY")
    return provider, key_name


def _write_backend_artifact(*, ok: bool, error: str | None = None) -> Path:
    path = ROOT / "reports" / "launch" / "backend_suite.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": _timestamp_to_text(_utc_now()),
        "backend_green": "green" if ok else "red",
        "ok": ok,
        "error": error,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _run_command(command: list[str], *, cwd: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part).strip()
    return completed.returncode == 0, output


def _run_fresh_checks() -> dict[str, str]:
    timestamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    shim_dir = ROOT / "debug_runs" / "launch_ops" / "provider_shim" / timestamp
    external_dir = ROOT / "debug_runs" / "launch_ops" / "external_provider" / timestamp

    ok, output = _run_command([sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT)
    _write_backend_artifact(ok=ok, error=None if ok else output)

    _run_command([str(ROOT / "scripts" / "eval:full")], cwd=ROOT)
    _run_command(
        [sys.executable, str(ROOT / "scripts" / "capture_ui_session.py"), "--provider-path", "provider_shim", "--out", str(shim_dir)],
        cwd=ROOT,
    )

    provider, key_name = _required_provider_env()
    if os.environ.get(key_name):
        _run_command(
            [
                sys.executable,
                str(ROOT / "scripts" / "capture_ui_session.py"),
                "--provider-path",
                "external_provider",
                "--out",
                str(external_dir),
            ],
            cwd=ROOT,
        )
        _run_command([str(ROOT / "scripts" / "eval:full"), "--real"], cwd=ROOT)
    return {
        "backend_artifact": str(ROOT / "reports" / "launch" / "backend_suite.json"),
        "shim_summary": str(shim_dir / "summary.json"),
        "external_summary": str(external_dir / "summary.json") if os.environ.get(key_name) else "",
        "provider": provider,
        "provider_env": key_name,
    }


def _green_from_harness(status: ArtifactStatus) -> str:
    if status.missing:
        return "not_run"
    if status.malformed or status.stale or status.payload is None:
        return "red"
    summary = dict(status.payload.get("summary") or {})
    if not summary:
        return "red"
    failed_cases = int(summary.get("failed_cases", 0) or 0)
    return "green" if failed_cases == 0 else "red"


def _green_from_capture(status: ArtifactStatus, *, key: str) -> str:
    if status.missing:
        return "not_run"
    if status.malformed or status.stale or status.payload is None:
        return "red"
    launch_gates = dict(status.payload.get("launch_gates") or {})
    value = str(launch_gates.get(key) or "").strip()
    return value if value in {"green", "red", "not_run"} else "red"


def _artifact_sources(
    *,
    backend: ArtifactStatus,
    stub_harness: ArtifactStatus,
    external_harness: ArtifactStatus,
    shim_capture: ArtifactStatus,
    external_capture: ArtifactStatus,
    smoke_summary: ArtifactStatus,
) -> dict[str, str | None]:
    return {
        "backend": backend.path,
        "provider_stub_harness": stub_harness.path,
        "external_provider_harness": external_harness.path,
        "provider_shim_capture": shim_capture.path,
        "external_provider_capture": external_capture.path,
        "localhost_smoke": smoke_summary.path,
    }


def _primary_counts_source(stub_harness: ArtifactStatus, external_harness: ArtifactStatus) -> ArtifactStatus:
    if not external_harness.missing:
        return external_harness
    return stub_harness


def _provider_source(
    *,
    stub_harness: ArtifactStatus,
    shim_capture: ArtifactStatus,
    external_capture: ArtifactStatus,
    external_harness: ArtifactStatus,
) -> str:
    if not external_capture.missing or not external_harness.missing:
        return "external_provider"
    if not shim_capture.missing:
        return "provider_shim"
    if not stub_harness.missing:
        return "provider_stub"
    return "provider_stub"


def _final_recommendation(
    *,
    launch_mode: str,
    backend_green: str,
    harness_green: str,
    shim_green: str,
    provider_green: str,
    remix_green: str,
    required_field_miss_count: int,
    under_length_miss_count: int,
) -> str:
    if (
        backend_green != "green"
        or harness_green != "green"
        or required_field_miss_count > 0
        or under_length_miss_count > 0
        or "red" in {shim_green, provider_green, remix_green}
    ):
        return "Not yet launch-ready"

    if launch_mode == "broad_launch":
        if shim_green == "green" and provider_green == "green" and remix_green == "green":
            return "Stable for broad launch"
        return "Not yet launch-ready"

    if launch_mode == "limited_rollout":
        if shim_green == "green" and remix_green == "green" and provider_green in {"green", "not_run"}:
            return "Stable for MVP launch behind limited rollout"
        if shim_green == "not_run" or remix_green == "not_run":
            return "Stable for broader MVP work"
        return "Not yet launch-ready"

    if backend_green == "green" and harness_green == "green":
        return "Stable for broader MVP work"
    return "Not yet launch-ready"


def _write_launch_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Launch Check",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Launch mode: `{report['launch_mode']}`",
        f"- Final recommendation: `{report['final_recommendation']}`",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| backend_green | `{report['backend_green']}` |",
        f"| harness_green | `{report['harness_green']}` |",
        f"| shim_green | `{report['shim_green']}` |",
        f"| provider_green | `{report['provider_green']}` |",
        f"| remix_green | `{report['remix_green']}` |",
        f"| provider_source | `{report['provider_source']}` |",
        f"| required_field_miss_count | {report['required_field_miss_count']} |",
        f"| under_length_miss_count | {report['under_length_miss_count']} |",
        f"| claims_policy_intervention_count | {report['claims_policy_intervention_count']} |",
        "",
        "## Top Violation Codes",
        "",
    ]
    top_codes = dict(report.get("top_violation_codes") or {})
    if top_codes:
        for code, count in top_codes.items():
            lines.append(f"- `{code}`: {count}")
    else:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Artifact Sources",
            "",
        ]
    )
    for name, artifact_path in dict(report.get("artifact_sources") or {}).items():
        lines.append(f"- `{name}`: `{artifact_path or 'missing'}`")
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- `{error}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_launch_report(*, localhost_smoke_summary: str, max_age_hours: int) -> dict[str, Any]:
    max_age = timedelta(hours=max(1, max_age_hours))
    backend = _artifact_status(ROOT / "reports" / "launch" / "backend_suite.json", max_age=max_age)
    stub_harness = _artifact_status(ROOT / "reports" / "provider_stub" / "latest.json", max_age=max_age)
    if stub_harness.missing:
        stub_harness = _artifact_status(ROOT / "reports" / "latest.json", max_age=max_age)
    external_harness = _artifact_status(ROOT / "reports" / "external_provider" / "latest.json", max_age=max_age)
    shim_capture = _latest_json(
        [ROOT / "debug_runs" / "ui_sessions", ROOT / "debug_runs" / "ui_sessions_codex", ROOT / "debug_runs" / "launch_ops" / "provider_shim"],
        max_age=max_age,
        predicate=lambda payload: str(payload.get("provider_source") or "") == "provider_shim",
    )
    external_capture = _latest_json(
        [ROOT / "debug_runs" / "ui_sessions", ROOT / "debug_runs" / "ui_sessions_codex", ROOT / "debug_runs" / "launch_ops" / "external_provider"],
        max_age=max_age,
        predicate=lambda payload: str(payload.get("provider_source") or "") == "external_provider",
    )
    smoke_summary = (
        _artifact_status(Path(localhost_smoke_summary).resolve(), max_age=max_age)
        if localhost_smoke_summary.strip()
        else ArtifactStatus(path=None, payload=None, timestamp=None, stale=False, malformed=False, missing=True)
    )

    errors: list[str] = []
    for label, status in {
        "backend": backend,
        "provider_stub_harness": stub_harness,
        "external_provider_harness": external_harness,
        "provider_shim_capture": shim_capture,
        "external_provider_capture": external_capture,
        "localhost_smoke": smoke_summary,
    }.items():
        if status.malformed:
            errors.append(f"{label}:malformed:{status.error}")
        elif status.stale:
            errors.append(f"{label}:stale:{status.path}")

    backend_green = "not_run" if backend.missing else "red" if backend.malformed or backend.stale else str((backend.payload or {}).get("backend_green") or "red")
    harness_green = _green_from_harness(stub_harness)
    shim_green = _green_from_capture(shim_capture, key="shim_green")
    external_capture_green = _green_from_capture(external_capture, key="provider_green")
    external_harness_green = _green_from_harness(external_harness)
    if external_capture_green == "green" or external_harness_green == "green":
        provider_green = "green"
    elif external_capture_green == "red" or external_harness_green == "red":
        provider_green = "red"
    else:
        provider_green = "not_run"

    remix_source = external_capture if not external_capture.missing else shim_capture
    remix_green = _green_from_capture(remix_source, key="remix_green")

    counts_source = _primary_counts_source(stub_harness, external_harness)
    counts_summary = dict((counts_source.payload or {}).get("summary") or {})
    report = {
        "generated_at": _timestamp_to_text(_utc_now()),
        "launch_mode": runtime_launch_mode(),
        "backend_green": backend_green,
        "harness_green": harness_green,
        "shim_green": shim_green,
        "provider_green": provider_green,
        "remix_green": remix_green,
        "provider_source": _provider_source(
            stub_harness=stub_harness,
            shim_capture=shim_capture,
            external_capture=external_capture,
            external_harness=external_harness,
        ),
        "required_field_miss_count": int(counts_summary.get("required_field_miss_count", 0) or 0),
        "under_length_miss_count": int(counts_summary.get("under_length_miss_count", 0) or 0),
        "top_violation_codes": dict(counts_summary.get("top_violation_codes") or {}),
        "claims_policy_intervention_count": int(counts_summary.get("claims_policy_intervention_count", 0) or 0),
        "final_recommendation": "",
        "artifact_sources": _artifact_sources(
            backend=backend,
            stub_harness=stub_harness,
            external_harness=external_harness,
            shim_capture=shim_capture,
            external_capture=external_capture,
            smoke_summary=smoke_summary,
        ),
        "errors": errors,
    }
    report["final_recommendation"] = _final_recommendation(
        launch_mode=report["launch_mode"],
        backend_green=report["backend_green"],
        harness_green=report["harness_green"],
        shim_green=report["shim_green"],
        provider_green=report["provider_green"],
        remix_green=report["remix_green"],
        required_field_miss_count=report["required_field_miss_count"],
        under_length_miss_count=report["under_length_miss_count"],
    )
    return report


def _write_launch_report(report: dict[str, Any]) -> tuple[Path, Path]:
    report_dir = ROOT / "reports" / "launch"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "latest.json"
    md_path = report_dir / "latest.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_launch_markdown(report, md_path)
    return json_path, md_path


def main() -> int:
    args = _parse_args()
    if not args.from_artifacts:
        _run_fresh_checks()
    report = _read_launch_report(
        localhost_smoke_summary=args.localhost_smoke_summary,
        max_age_hours=args.max_age_hours,
    )
    json_path, md_path = _write_launch_report(report)
    print(
        json.dumps(
            {
                "launch_artifact_json": str(json_path),
                "launch_artifact_md": str(md_path),
                "final_recommendation": report["final_recommendation"],
                "provider_source": report["provider_source"],
            },
            indent=2,
        )
    )
    return 0 if report["final_recommendation"] != "Not yet launch-ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
