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

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in some environments
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from runtime_debug import build_runtime_debug_payload
from runtime_debug import validate_runtime_debug_payload


DEFAULT_MAX_AGE_HOURS = 72
DEFAULT_RECOMMENDED_MAX_AGE_HOURS = 48
_PROD_APP_ENVS = {"staging", "prod", "production"}
_RELEASE_FINGERPRINT_FIELDS = ("git_sha", "build_id", "image_tag", "release_version")
_LAUNCH_MODES_REQUIRING_DURABLE_REDIS = {"limited_rollout", "broad_launch"}
_DURABLE_REDIS_STATES = {"external_redis_configured"}
_DURABLE_DATABASE_STATES = {"external_postgres_configured"}
_DURABLE_VECTOR_STATES = {"pgvector_configured"}
_LOCAL_DATABASE_STATES = {"default_local_sqlite", "local_sqlite", "local_postgres"}
_NON_DURABLE_VECTOR_STATES = {"memory_backend", "pinecone_missing_config", "pgvector_missing_postgres_config"}


@dataclass
class ArtifactStatus:
    path: str | None
    payload: dict[str, Any] | None
    timestamp: datetime | None
    stale: bool
    malformed: bool
    missing: bool
    error: str | None = None
    schema_incomplete: bool = False
    schema_messages: list[str] | None = None
    schema_warnings: list[str] | None = None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute EmailDJ launch readiness.")
    default_staging_debug_config_path = ROOT / "reports" / "launch" / "runtime_snapshots" / "staging.json"
    default_production_debug_config_path = ROOT / "reports" / "launch" / "runtime_snapshots" / "production.json"
    parser.add_argument("--from-artifacts", action="store_true", help="Read existing artifacts only.")
    parser.add_argument(
        "--allow-not-ready",
        action="store_true",
        help="Write the launch report and exit 0 even when known readiness gates still block launch.",
    )
    parser.add_argument(
        "--localhost-smoke-summary",
        default="",
        help="Optional path to a localhost smoke summary.json artifact to include.",
    )
    parser.add_argument(
        "--staging-debug-config",
        default=str(default_staging_debug_config_path),
        help=(
            "Path to the approved staging /web/v1/debug/config snapshot "
            f"(default: {default_staging_debug_config_path})."
        ),
    )
    parser.add_argument(
        "--production-debug-config",
        default=str(default_production_debug_config_path),
        help=(
            "Path to the production /web/v1/debug/config snapshot "
            f"(default: {default_production_debug_config_path})."
        ),
    )
    parser.add_argument(
        "--max-age-hours",
        type=int,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Hard artifact freshness threshold in hours (default: {DEFAULT_MAX_AGE_HOURS}).",
    )
    parser.add_argument(
        "--recommended-max-age-hours",
        type=int,
        default=DEFAULT_RECOMMENDED_MAX_AGE_HOURS,
        help=(
            "Recommended freshness threshold in hours for launch-day judgment "
            f"(default: {DEFAULT_RECOMMENDED_MAX_AGE_HOURS})."
        ),
    )
    return parser.parse_args()


def _load_launch_env() -> None:
    load_dotenv(dotenv_path=ROOT / ".env", override=False)


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


def _artifact_timestamp(payload: dict[str, Any], *, prefer_capture: bool = False) -> datetime | None:
    keys = ("captured_at_utc", "generated_at", "generated_at_utc", "timestamp_utc") if prefer_capture else (
        "generated_at",
        "generated_at_utc",
        "captured_at_utc",
        "timestamp_utc",
    )
    for key in keys:
        parsed = _parse_timestamp(payload.get(key))
        if parsed is not None:
            return parsed
    return None


def _artifact_status(path: Path, *, max_age: timedelta, prefer_capture_timestamp: bool = False) -> ArtifactStatus:
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
    timestamp = _artifact_timestamp(payload, prefer_capture=prefer_capture_timestamp)
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


def _runtime_snapshot_status(path: Path, *, max_age: timedelta, label: str) -> ArtifactStatus:
    status = _artifact_status(path, max_age=max_age, prefer_capture_timestamp=True)
    if status.missing or status.malformed or status.payload is None:
        return status

    validation = validate_runtime_debug_payload(status.payload)
    schema_messages: list[str] = []
    missing_critical = list(validation["missing_critical"])
    if missing_critical:
        schema_messages.append(f"missing_required_runtime_fields:{','.join(missing_critical)}")
    if validation["release_identity_present"] and not validation["release_identity_populated"]:
        schema_messages.append("release_identity_values_empty")

    schema_warnings: list[str] = []
    missing_recommended = list(validation["missing_recommended"])
    if missing_recommended:
        schema_warnings.append(f"{label}_runtime_snapshot_missing_recommended_fields:{','.join(missing_recommended)}")
    if validation["release_identity_present"] and not validation["release_identity_populated"]:
        schema_warnings.append("release_fingerprint_unavailable")

    if missing_critical:
        status.schema_incomplete = True
        status.error = ";".join(schema_messages)
    status.schema_messages = schema_messages
    status.schema_warnings = schema_warnings
    return status


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
        if (status.timestamp or datetime.min.replace(tzinfo=timezone.utc)) > (
            best.timestamp or datetime.min.replace(tzinfo=timezone.utc)
        ):
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


def _artifact_sources(**statuses: ArtifactStatus) -> dict[str, str | None]:
    return {name: status.path for name, status in statuses.items()}


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


def _runtime_payload(status: ArtifactStatus) -> dict[str, Any] | None:
    if status.missing or status.malformed or status.stale or status.payload is None:
        return None
    if status.schema_incomplete:
        return None
    return dict(status.payload)


def _artifact_age_hours(status: ArtifactStatus) -> float | None:
    if status.timestamp is None:
        return None
    age = _utc_now() - status.timestamp
    return round(age.total_seconds() / 3600, 2)


def _artifact_provenance(
    label: str,
    status: ArtifactStatus,
    *,
    recommended_max_age: timedelta,
) -> dict[str, Any]:
    age_hours = _artifact_age_hours(status)
    warning_threshold_exceeded = False
    if age_hours is not None:
        warning_threshold_exceeded = age_hours > (recommended_max_age.total_seconds() / 3600)
    return {
        "label": label,
        "path": status.path,
        "timestamp": _timestamp_to_text(status.timestamp),
        "age_hours": age_hours,
        "missing": status.missing,
        "malformed": status.malformed,
        "schema_incomplete": status.schema_incomplete,
        "stale": status.stale,
        "warning_threshold_exceeded": warning_threshold_exceeded and not status.stale,
        "error": status.error,
        "schema_messages": list(status.schema_messages or []),
        "schema_warnings": list(status.schema_warnings or []),
    }


def _int_field(payload: dict[str, Any], key: str) -> int:
    try:
        return int(payload.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _localhost_smoke_evidence(status: ArtifactStatus) -> dict[str, Any]:
    if status.missing:
        return {
            "green": "not_run",
            "state": "missing",
            "path": status.path,
            "timestamp": None,
            "mode": None,
            "total": 0,
            "pass": 0,
            "fail": 0,
            "errors": 0,
            "pass_rate_pct": None,
            "provider_source_counts": {},
            "launch_gates": {},
        }
    if status.malformed or status.stale or status.payload is None:
        return {
            "green": "red",
            "state": "invalid",
            "path": status.path,
            "timestamp": _timestamp_to_text(status.timestamp),
            "mode": None,
            "total": 0,
            "pass": 0,
            "fail": 0,
            "errors": 0,
            "pass_rate_pct": None,
            "provider_source_counts": {},
            "launch_gates": {},
        }

    payload = status.payload
    total = _int_field(payload, "total")
    pass_count = _int_field(payload, "pass")
    fail_count = _int_field(payload, "fail")
    error_count = _int_field(payload, "errors")
    green = "green" if total > 0 and pass_count == total and fail_count == 0 and error_count == 0 else "red"
    return {
        "green": green,
        "state": "present",
        "path": status.path,
        "timestamp": _timestamp_to_text(status.timestamp),
        "mode": payload.get("mode"),
        "total": total,
        "pass": pass_count,
        "fail": fail_count,
        "errors": error_count,
        "pass_rate_pct": payload.get("pass_rate_pct"),
        "provider_source_counts": dict(payload.get("provider_source_counts") or {}),
        "launch_gates": dict(payload.get("launch_gates") or {}),
    }


def _recommended_age_warnings(
    artifact_statuses: dict[str, ArtifactStatus],
    *,
    recommended_max_age: timedelta,
) -> list[str]:
    threshold_hours = recommended_max_age.total_seconds() / 3600
    warnings: list[str] = []
    for label, status in artifact_statuses.items():
        age_hours = _artifact_age_hours(status)
        if (
            status.missing
            or status.malformed
            or status.stale
            or age_hours is None
            or age_hours <= threshold_hours
        ):
            continue
        warnings.append(f"artifact_age_exceeds_recommended_window:{label}")
    return warnings


def _release_fields(payload: dict[str, Any] | None) -> dict[str, str | None]:
    data = dict(payload or {})
    return {
        field: (str(data.get(field) or "").strip() or None)
        for field in _RELEASE_FINGERPRINT_FIELDS
    }


def _release_comparison(
    *,
    staging_snapshot: ArtifactStatus,
    production_snapshot: ArtifactStatus,
    runtime_source_used: str,
) -> tuple[list[str], list[str], dict[str, Any]]:
    blockers: list[str] = []
    warnings: list[str] = []
    staging_payload = _runtime_payload(staging_snapshot)
    production_payload = _runtime_payload(production_snapshot)

    if staging_snapshot.missing:
        warnings.append("staging_runtime_snapshot_missing")
    elif staging_snapshot.schema_incomplete:
        warnings.append("staging_runtime_snapshot_schema_incomplete")
    if production_snapshot.missing:
        warnings.append("production_runtime_snapshot_missing")
    elif production_snapshot.schema_incomplete:
        warnings.append("production_runtime_snapshot_schema_incomplete")
    if runtime_source_used == "local_env":
        warnings.append("runtime_parity_evaluated_from_local_env_only")

    staging_fields = _release_fields(staging_payload)
    production_fields = _release_fields(production_payload)
    comparable_fields = [
        field
        for field in _RELEASE_FINGERPRINT_FIELDS
        if staging_fields.get(field) and production_fields.get(field)
    ]
    if runtime_source_used != "production_runtime_snapshot" or not comparable_fields:
        warnings.append("release_fingerprint_unavailable")
    else:
        for field in comparable_fields:
            if staging_fields[field] != production_fields[field]:
                blockers.append(
                    f"release_fingerprint_mismatch:{field}:{staging_fields[field]}->{production_fields[field]}"
                )

    return blockers, warnings, {
        "runtime_source_used": runtime_source_used,
        "staging": staging_fields,
        "production": production_fields if runtime_source_used == "production_runtime_snapshot" else None,
        "comparison_fields": comparable_fields,
    }


def _config_findings(runtime_data: dict[str, Any]) -> tuple[list[str], list[str]]:
    launch_mode = str(runtime_data.get("launch_mode") or "").strip()
    app_env = str(runtime_data.get("app_env") or "").strip()
    configured_mode = str(runtime_data.get("configured_quick_generate_mode") or "").strip().lower()
    effective_mode = str(runtime_data.get("effective_quick_generate_mode") or runtime_data.get("runtime_mode") or "").strip().lower()
    route_gates = dict(runtime_data.get("route_gates") or {})
    route_gate_sources = dict(runtime_data.get("route_gate_sources") or {})
    effective_provider_source = str(runtime_data.get("effective_provider_source") or "").strip()
    chrome_extension_origin_state = str(runtime_data.get("chrome_extension_origin_state") or "unset").strip()
    web_app_origin_state = str(runtime_data.get("web_app_origin_state") or "unset").strip()
    beta_keys_state = str(runtime_data.get("beta_keys_state") or "unset").strip()
    redis_config_state = str(runtime_data.get("redis_config_state") or "unknown").strip()
    database_config_state = str(runtime_data.get("database_config_state") or "unknown").strip()
    vector_store_config_state = str(runtime_data.get("vector_store_config_state") or "unknown").strip()
    validation_fallback_allowed = bool(runtime_data.get("validation_fallback_allowed"))

    blockers: list[str] = []
    if bool(runtime_data.get("provider_stub_enabled")) and launch_mode in {"limited_rollout", "broad_launch"}:
        blockers.append(f"provider_stub_enabled_for_launch_mode:{launch_mode}")
    if configured_mode and effective_mode and configured_mode != effective_mode:
        blockers.append(f"configured_quick_generate_mode_mismatch:{configured_mode}->{effective_mode}")
    if launch_mode == "limited_rollout" and effective_provider_source != "external_provider":
        blockers.append(f"resolved_provider_source_not_external_provider:{effective_provider_source or 'unset'}")
    if launch_mode == "limited_rollout" and route_gates.get("preview") is True:
        blockers.append("preview_route_enabled_for_launch_mode:limited_rollout")
    if launch_mode == "limited_rollout" and chrome_extension_origin_state != "explicit_pinned":
        blockers.append(f"chrome_extension_origin_not_pinned:{chrome_extension_origin_state}")
    if launch_mode == "limited_rollout" and web_app_origin_state != "explicit_pinned":
        blockers.append(f"web_app_origin_not_pinned:{web_app_origin_state}")
    if launch_mode == "limited_rollout" and beta_keys_state != "explicit_pinned":
        blockers.append(f"beta_keys_not_safe:{beta_keys_state}")
    if launch_mode in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS and redis_config_state not in _DURABLE_REDIS_STATES:
        blockers.append(f"redis_not_durable_for_launch_mode:{launch_mode}:{redis_config_state}")
    if launch_mode in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS and database_config_state not in _DURABLE_DATABASE_STATES:
        blockers.append(f"database_not_durable_for_launch_mode:{launch_mode}:{database_config_state}")
    if launch_mode in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS and vector_store_config_state not in _DURABLE_VECTOR_STATES:
        blockers.append(f"vector_store_not_durable_for_launch_mode:{launch_mode}:{vector_store_config_state}")
    if launch_mode in {"limited_rollout", "broad_launch"} and validation_fallback_allowed:
        blockers.append(f"validation_fallback_enabled_for_launch_mode:{launch_mode}")

    warnings: list[str] = []
    if app_env not in _PROD_APP_ENVS:
        warnings.append(f"app_env_not_prod_like:{app_env}")
    for route_name in ("generate", "remix"):
        if route_gate_sources.get(route_name) == "explicit_env" and route_gates.get(route_name) is False:
            warnings.append(f"{route_name}_disabled_explicitly")
    if str(runtime_data.get("web_rate_limit_source") or "").strip() != "explicit_env":
        warnings.append("web_rate_limit_default_drift_unpinned")
    if database_config_state in _LOCAL_DATABASE_STATES and launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        warnings.append(f"database_not_durable:{database_config_state}")
    elif database_config_state == "unknown" and launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        warnings.append("database_config_state_unavailable")
    if vector_store_config_state in _NON_DURABLE_VECTOR_STATES and launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        warnings.append(f"vector_store_not_durable:{vector_store_config_state}")
    elif vector_store_config_state == "unknown" and launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        warnings.append("vector_store_config_state_unavailable")
    if "validation_fallback_allowed" not in runtime_data:
        warnings.append("validation_fallback_policy_unavailable")
    return blockers, warnings


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
    config_blockers: list[str],
    errors: list[str],
) -> str:
    if (
        bool(config_blockers)
        or bool(errors)
        or backend_green != "green"
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
    runtime_reference = dict(report.get("runtime_reference") or {})
    release_parity = dict(report.get("release_fingerprint_parity") or {})
    localhost_smoke = dict(report.get("localhost_smoke") or {})
    artifact_provenance = dict(report.get("artifact_provenance") or {})
    origin_fields = {
        "chrome_extension_origin": report.get("chrome_extension_origin"),
        "chrome_extension_origin_state": report.get("chrome_extension_origin_state"),
        "web_app_origin": report.get("web_app_origin"),
        "web_app_origin_state": report.get("web_app_origin_state"),
        "beta_keys_state": report.get("beta_keys_state"),
        "web_rate_limit_per_min": report.get("web_rate_limit_per_min"),
        "web_rate_limit_source": report.get("web_rate_limit_source"),
    }
    infra_fields = {
        "redis_config_state": report.get("redis_config_state"),
        "database_config_state": report.get("database_config_state"),
        "vector_store_config_state": report.get("vector_store_config_state"),
        "vector_store_backend": report.get("vector_store_backend"),
    }

    lines = [
        "# Launch Check",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Launch mode: `{report['launch_mode']}`",
        f"- Final recommendation: `{report['final_recommendation']}`",
        f"- Hard freshness threshold (hours): `{report['max_age_hours']}`",
        f"- Recommended freshness threshold (hours): `{report['recommended_max_age_hours']}`",
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
            "## Release Fingerprint Parity",
            "",
            f"- `runtime_source_used`: `{release_parity.get('runtime_source_used') or 'unknown'}`",
            f"- `staging`: `{json.dumps(release_parity.get('staging') or {}, sort_keys=True)}`",
            f"- `production`: `{json.dumps(release_parity.get('production') or {}, sort_keys=True)}`",
            f"- `comparison_fields`: `{json.dumps(release_parity.get('comparison_fields') or [])}`",
            "",
            "## Resolved Runtime Path",
            "",
            f"- `runtime_source_used`: `{runtime_reference.get('runtime_source_used') or 'unknown'}`",
            f"- `app_env`: `{report['app_env']}`",
            f"- `runtime_mode`: `{report['runtime_mode']}`",
            f"- `configured_quick_generate_mode`: `{report['configured_quick_generate_mode'] or 'unset'}`",
            f"- `effective_quick_generate_mode`: `{report['effective_quick_generate_mode']}`",
            f"- `provider_stub_enabled`: `{report['provider_stub_enabled']}`",
            f"- `real_provider_preference`: `{report['real_provider_preference']}`",
            f"- `effective_provider_source`: `{report['effective_provider_source']}`",
            f"- `effective_provider_model_identifier`: `{report['effective_model_identifier']}`",
            f"- `validation_fallback_allowed`: `{report['validation_fallback_allowed']}`",
            f"- `validation_fallback_policy`: `{report['validation_fallback_policy'] or 'unset'}`",
            f"- `preview_pipeline_enabled`: `{report['preview_pipeline_enabled']}`",
            f"- `route_gates`: `{json.dumps(report['route_gates'], sort_keys=True)}`",
            f"- `route_gate_sources`: `{json.dumps(report['route_gate_sources'], sort_keys=True)}`",
            "",
            "## Preview Route Invariant",
            "",
            f"- `preview_enabled`: `{bool(report['route_gates'].get('preview'))}`",
            f"- `preview_gate_source`: `{report['route_gate_sources'].get('preview', 'unknown')}`",
        ]
    )
    if "preview_route_enabled_for_launch_mode:limited_rollout" in report.get("config_blockers", []):
        lines.append("- `limited_rollout_blocker`: `preview_route_enabled_for_launch_mode:limited_rollout`")
    else:
        lines.append("- `limited_rollout_blocker`: `none`")

    lines.extend(
        [
            "",
            "## Localhost Smoke Evidence",
            "",
            f"- `green`: `{localhost_smoke.get('green') or 'not_run'}`",
            f"- `state`: `{localhost_smoke.get('state') or 'missing'}`",
            f"- `mode`: `{localhost_smoke.get('mode') or 'unset'}`",
            f"- `total`: {localhost_smoke.get('total') or 0}",
            f"- `pass`: {localhost_smoke.get('pass') or 0}",
            f"- `fail`: {localhost_smoke.get('fail') or 0}",
            f"- `errors`: {localhost_smoke.get('errors') or 0}",
            f"- `pass_rate_pct`: `{localhost_smoke.get('pass_rate_pct') if localhost_smoke.get('pass_rate_pct') is not None else 'n/a'}`",
            f"- `provider_source_counts`: `{json.dumps(localhost_smoke.get('provider_source_counts') or {}, sort_keys=True)}`",
            f"- `launch_gates`: `{json.dumps(localhost_smoke.get('launch_gates') or {}, sort_keys=True)}`",
        ]
    )

    lines.extend(["", "## Artifact Freshness And Provenance", ""])
    for label, summary in artifact_provenance.items():
        lines.append(
            "- "
            f"`{label}` path=`{summary.get('path') or 'missing'}` "
            f"timestamp=`{summary.get('timestamp') or 'missing'}` "
            f"age_hours=`{summary.get('age_hours') if summary.get('age_hours') is not None else 'n/a'}` "
            f"stale=`{summary.get('stale')}` "
            f"malformed=`{summary.get('malformed')}` "
            f"schema_incomplete=`{summary.get('schema_incomplete')}` "
            f"missing=`{summary.get('missing')}`"
        )
        if summary.get("error"):
            lines.append(f"- `{label}_error`: `{summary.get('error')}`")

    lines.extend(["", "## Origin And Beta-Key Safety", ""])
    for field, value in origin_fields.items():
        lines.append(f"- `{field}`: `{value if value is not None else 'unset'}`")

    lines.extend(["", "## Durable Infra Readiness", ""])
    for field, value in infra_fields.items():
        lines.append(f"- `{field}`: `{value if value is not None else 'unset'}`")

    lines.extend(["", "## Config Blockers", ""])
    blockers = list(report.get("config_blockers") or [])
    if blockers:
        for blocker in blockers:
            lines.append(f"- `{blocker}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Config Warnings", ""])
    warnings = list(report.get("config_warnings") or [])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning}`")
    else:
        lines.append("- None")

    lines.extend(["", "## Artifact Sources", ""])
    for name, artifact_path in dict(report.get("artifact_sources") or {}).items():
        lines.append(f"- `{name}`: `{artifact_path or 'missing'}`")
    if report.get("errors"):
        lines.extend(["", "## Errors", ""])
        for error in report["errors"]:
            lines.append(f"- `{error}`")
    operator_next_steps = list(report.get("operator_next_steps") or [])
    if operator_next_steps:
        lines.extend(["", "## Operator Next Steps", ""])
        for step in operator_next_steps:
            lines.append(f"- {step}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _snapshot_path(raw_path: str, default_path: Path) -> Path:
    value = (raw_path or "").strip()
    return Path(value).resolve() if value else default_path


def _default_snapshot_path(kind: str) -> Path:
    return ROOT / "reports" / "launch" / "runtime_snapshots" / f"{kind}.json"


def _capture_command_for(label: str) -> str:
    base_var = "$STAGING_BASE_URL" if label == "staging" else "$PROD_BASE_URL"
    return (
        "./.venv/bin/python scripts/capture_runtime_snapshot.py "
        f'--label {label} --url "{base_var}" --header "x-emaildj-beta-key: $BETA_KEY"'
    )


def _has_blocker(report: dict[str, Any], prefix: str) -> bool:
    return any(str(blocker).startswith(prefix) for blocker in report.get("config_blockers") or [])


def _artifact_needs_operator_refresh(report: dict[str, Any], label: str) -> bool:
    artifact = dict((report.get("artifact_provenance") or {}).get(label) or {})
    return bool(
        artifact.get("missing")
        or artifact.get("stale")
        or artifact.get("malformed")
        or artifact.get("schema_incomplete")
    )


def _operator_next_steps(report: dict[str, Any], *, staging_snapshot: ArtifactStatus, production_snapshot: ArtifactStatus) -> list[str]:
    steps: list[str] = []
    if _has_blocker(report, "web_app_origin_not_pinned:"):
        steps.append(
            "Set `WEB_APP_ORIGIN` to the deployed web-app origin for the target launch environment, then re-capture staging and production runtime snapshots."
        )
    if _has_blocker(report, "chrome_extension_origin_not_pinned:"):
        steps.append(
            "Set `CHROME_EXTENSION_ORIGIN` to the deployed Chrome extension origin (`chrome-extension://<extension-id>`), then re-capture staging and production runtime snapshots."
        )
    if _has_blocker(report, "beta_keys_not_safe:"):
        steps.append(
            "Set `EMAILDJ_WEB_BETA_KEYS` to explicit non-dev beta key values and use one matching value as `$BETA_KEY` for runtime snapshot capture and localhost/deployed smoke checks."
        )
    if _has_blocker(report, "redis_not_durable_for_launch_mode:"):
        steps.append(
            "Provision managed Redis for the launch environment, set `REDIS_URL`, and ensure `REDIS_FORCE_INMEMORY` is unset or `0` before re-running launch checks."
        )
    if _has_blocker(report, "database_not_durable_for_launch_mode:"):
        steps.append(
            "Provision managed Postgres for the launch environment, set `DATABASE_URL` to the deployed database, and re-capture staging and production runtime snapshots."
        )
    if _has_blocker(report, "vector_store_not_durable_for_launch_mode:"):
        steps.append(
            "Set `VECTOR_STORE_BACKEND=pgvector` for the launch environment after managed Postgres is configured, then re-capture staging and production runtime snapshots."
        )
    if _has_blocker(report, "provider_stub_enabled_for_launch_mode:") or _has_blocker(
        report, "resolved_provider_source_not_external_provider:"
    ):
        steps.append(
            "Set `USE_PROVIDER_STUB=0` with a real provider configured so limited rollout resolves to `effective_provider_source=external_provider`."
        )
    if _has_blocker(report, "configured_quick_generate_mode_mismatch:"):
        steps.append(
            "Align `EMAILDJ_QUICK_GENERATE_MODE` with the resolved runtime mode, or remove the override and let launch mode choose the effective real-provider path."
        )
    if _has_blocker(report, "preview_route_enabled_for_launch_mode:limited_rollout"):
        steps.append(
            "Keep preview disabled for `limited_rollout` by removing any explicit preview-route override before recapturing runtime snapshots."
        )
    if _has_blocker(report, "validation_fallback_enabled_for_launch_mode:"):
        steps.append(
            "Disable deterministic validation fallback for launch mode; launch environments must fail closed on CTCO validation failure."
        )
    if _artifact_needs_operator_refresh(report, "localhost_smoke"):
        steps.append(
            "Run the guarded localhost smoke against the intended Hub API process with `EMAILDJ_CONFIRM_LOCALHOST_SMOKE=1 make localhost-smoke`, then rerun `make launch-check`."
        )
    if _has_blocker(report, "localhost_smoke_not_green:"):
        steps.append(
            "Investigate the failing localhost smoke cases, fix the harness or generation path, then rerun `EMAILDJ_CONFIRM_LOCALHOST_SMOKE=1 make localhost-smoke`."
        )
    for label, status in (("staging", staging_snapshot), ("production", production_snapshot)):
        if status.missing:
            steps.append(
                f"Capture the {label} hub-api runtime snapshot using `{label}` backend URL "
                f"(`{'$STAGING_BASE_URL' if label == 'staging' else '$PROD_BASE_URL'}`) and a `BETA_KEY` value present in deployed `EMAILDJ_WEB_BETA_KEYS`: `{_capture_command_for(label)}`"
            )
            continue
        if status.stale:
            steps.append(
                f"Re-capture the stale {label} runtime snapshot with the backend URL "
                f"(`{'$STAGING_BASE_URL' if label == 'staging' else '$PROD_BASE_URL'}`) and matching `BETA_KEY`: `{_capture_command_for(label)}`"
            )
            continue
        if status.malformed or status.schema_incomplete:
            steps.append(
                f"Re-capture the invalid {label} hub-api runtime snapshot with the backend URL "
                f"(`{'$STAGING_BASE_URL' if label == 'staging' else '$PROD_BASE_URL'}`) and matching `BETA_KEY`: `{_capture_command_for(label)}`"
            )
    if any(str(blocker).startswith("release_fingerprint_mismatch:") for blocker in report.get("config_blockers") or []):
        steps.append(
            "Production runtime fingerprint differs from approved staging. Fix deployment parity, then re-capture the production snapshot and rerun `./.venv/bin/python scripts/launch_check.py --from-artifacts`."
        )
    return steps


def _read_launch_report(
    *,
    localhost_smoke_summary: str,
    max_age_hours: int,
    recommended_max_age_hours: int = DEFAULT_RECOMMENDED_MAX_AGE_HOURS,
    staging_debug_config: str = "",
    production_debug_config: str = "",
) -> dict[str, Any]:
    _load_launch_env()
    max_age = timedelta(hours=max(1, max_age_hours))
    recommended_max_age = timedelta(hours=max(1, recommended_max_age_hours))

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
    staging_snapshot = _runtime_snapshot_status(
        _snapshot_path(staging_debug_config, _default_snapshot_path("staging")),
        max_age=max_age,
        label="staging",
    )
    production_snapshot = _runtime_snapshot_status(
        _snapshot_path(production_debug_config, _default_snapshot_path("production")),
        max_age=max_age,
        label="production",
    )

    artifact_statuses = {
        "backend": backend,
        "provider_stub_harness": stub_harness,
        "external_provider_harness": external_harness,
        "provider_shim_capture": shim_capture,
        "external_provider_capture": external_capture,
        "localhost_smoke": smoke_summary,
        "staging_runtime_snapshot": staging_snapshot,
        "production_runtime_snapshot": production_snapshot,
    }

    errors: list[str] = []
    for label, status in artifact_statuses.items():
        if status.malformed:
            errors.append(f"{label}:malformed:{status.error}")
        elif status.schema_incomplete:
            errors.append(f"{label}:schema_incomplete:{status.error}")
        elif status.stale:
            errors.append(f"{label}:stale:{status.path}")

    backend_green = (
        "not_run" if backend.missing else "red" if backend.malformed or backend.stale else str((backend.payload or {}).get("backend_green") or "red")
    )
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

    runtime_source_used = "production_runtime_snapshot" if _runtime_payload(production_snapshot) else "local_env"
    runtime_data = _runtime_payload(production_snapshot) or build_runtime_debug_payload()
    config_blockers, config_warnings = _config_findings(runtime_data)
    release_blockers, release_warnings, release_parity = _release_comparison(
        staging_snapshot=staging_snapshot,
        production_snapshot=production_snapshot,
        runtime_source_used=runtime_source_used,
    )
    localhost_smoke = _localhost_smoke_evidence(smoke_summary)
    if localhost_smoke["green"] == "red":
        config_blockers.append(
            f"localhost_smoke_not_green:pass={localhost_smoke['pass']}:fail={localhost_smoke['fail']}:errors={localhost_smoke['errors']}"
        )
    localhost_provider_counts = dict(localhost_smoke.get("provider_source_counts") or {})
    if localhost_provider_counts and set(localhost_provider_counts) == {"provider_stub"}:
        config_warnings.append("localhost_smoke_provider_stub_only")
    config_blockers.extend(release_blockers)
    config_warnings.extend(release_warnings)
    config_warnings.extend(_recommended_age_warnings(artifact_statuses, recommended_max_age=recommended_max_age))
    config_warnings.extend(staging_snapshot.schema_warnings or [])
    config_warnings.extend(production_snapshot.schema_warnings or [])
    config_blockers = sorted(set(config_blockers))
    config_warnings = sorted(set(config_warnings))

    report = {
        "generated_at": _timestamp_to_text(_utc_now()),
        "max_age_hours": max(1, max_age_hours),
        "recommended_max_age_hours": max(1, recommended_max_age_hours),
        "app_env": runtime_data.get("app_env"),
        "runtime_mode": runtime_data.get("runtime_mode") or runtime_data.get("effective_quick_generate_mode"),
        "configured_quick_generate_mode": runtime_data.get("configured_quick_generate_mode"),
        "effective_quick_generate_mode": runtime_data.get("effective_quick_generate_mode")
        or runtime_data.get("runtime_mode"),
        "provider_stub_enabled": bool(runtime_data.get("provider_stub_enabled")),
        "real_provider_preference": runtime_data.get("real_provider_preference"),
        "effective_provider_source": runtime_data.get("effective_provider_source"),
        "effective_provider": runtime_data.get("effective_provider"),
        "effective_model": runtime_data.get("effective_model"),
        "effective_model_identifier": runtime_data.get("effective_model_identifier"),
        "validation_fallback_allowed": bool(runtime_data.get("validation_fallback_allowed")),
        "validation_fallback_policy": runtime_data.get("validation_fallback_policy"),
        "launch_mode": runtime_data.get("launch_mode"),
        "route_gates": dict(runtime_data.get("route_gates") or {}),
        "route_gate_sources": dict(runtime_data.get("route_gate_sources") or {}),
        "preview_pipeline_enabled": bool(runtime_data.get("preview_pipeline_enabled")),
        "release_fingerprint": runtime_data.get("release_fingerprint"),
        "release_fingerprint_available": bool(runtime_data.get("release_fingerprint_available")),
        **_release_fields(runtime_data),
        "chrome_extension_origin": runtime_data.get("chrome_extension_origin"),
        "chrome_extension_origin_state": runtime_data.get("chrome_extension_origin_state"),
        "web_app_origin": runtime_data.get("web_app_origin"),
        "web_app_origin_state": runtime_data.get("web_app_origin_state"),
        "beta_keys_state": runtime_data.get("beta_keys_state"),
        "web_rate_limit_per_min": runtime_data.get("web_rate_limit_per_min"),
        "web_rate_limit_source": runtime_data.get("web_rate_limit_source"),
        "redis_config_state": runtime_data.get("redis_config_state"),
        "database_config_state": runtime_data.get("database_config_state"),
        "vector_store_config_state": runtime_data.get("vector_store_config_state"),
        "vector_store_backend": runtime_data.get("vector_store_backend"),
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
        "config_blockers": config_blockers,
        "config_warnings": config_warnings,
        "final_recommendation": "",
        "runtime_reference": {
            "runtime_source_used": runtime_source_used,
            "snapshot_path": production_snapshot.path if runtime_source_used == "production_runtime_snapshot" else None,
        },
        "release_fingerprint_parity": release_parity,
        "localhost_smoke": localhost_smoke,
        "artifact_sources": _artifact_sources(**artifact_statuses),
        "artifact_provenance": {
            label: _artifact_provenance(label, status, recommended_max_age=recommended_max_age)
            for label, status in artifact_statuses.items()
        },
        "errors": errors,
    }
    report["operator_next_steps"] = _operator_next_steps(
        report,
        staging_snapshot=staging_snapshot,
        production_snapshot=production_snapshot,
    )
    report["final_recommendation"] = _final_recommendation(
        launch_mode=str(report["launch_mode"] or ""),
        backend_green=report["backend_green"],
        harness_green=report["harness_green"],
        shim_green=report["shim_green"],
        provider_green=report["provider_green"],
        remix_green=report["remix_green"],
        required_field_miss_count=report["required_field_miss_count"],
        under_length_miss_count=report["under_length_miss_count"],
        config_blockers=report["config_blockers"],
        errors=report["errors"],
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
    _load_launch_env()
    args = _parse_args()
    if not args.from_artifacts:
        preflight_ok, preflight_output = _run_command(
            [sys.executable, str(ROOT / "scripts" / "launch_preflight.py")],
            cwd=ROOT,
        )
        if not preflight_ok:
            if preflight_output:
                print(preflight_output, file=sys.stderr)
            return 1
        _run_fresh_checks()
    report = _read_launch_report(
        localhost_smoke_summary=args.localhost_smoke_summary,
        max_age_hours=args.max_age_hours,
        recommended_max_age_hours=args.recommended_max_age_hours,
        staging_debug_config=args.staging_debug_config,
        production_debug_config=args.production_debug_config,
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
    if report["final_recommendation"] == "Not yet launch-ready" and not args.allow_not_ready:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
