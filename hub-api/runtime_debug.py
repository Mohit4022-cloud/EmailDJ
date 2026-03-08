"""Runtime debug helpers for deployment parity and launch verification."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from email_generation.model_cascade import get_model
from email_generation.runtime_policies import resolve_runtime_policies

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LOCAL_WEB_ORIGIN_HOSTS = {"localhost", "127.0.0.1"}
_RELEASE_IDENTITY_KEYS = (
    "release_fingerprint",
    "git_sha",
    "build_id",
    "image_tag",
    "release_version",
)
_RUNTIME_DEBUG_REQUIRED_FIELDS = (
    "generated_at_utc",
    "launch_mode",
    "runtime_mode",
    "provider_stub_enabled",
    "real_provider_preference",
    "effective_provider_source",
    "effective_quick_generate_mode",
    "chrome_extension_origin_state",
    "web_app_origin_state",
    "beta_keys_state",
)
_RUNTIME_DEBUG_RECOMMENDED_FIELDS = (
    "app_env",
    "preview_pipeline_enabled",
    "release_fingerprint_available",
    "web_rate_limit_per_min",
    "web_rate_limit_source",
    "effective_provider",
    "effective_model",
    "effective_model_identifier",
)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _env_value(*names: str) -> str | None:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


@lru_cache(maxsize=1)
def _git_sha_from_repo() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _release_fingerprint_fields() -> dict[str, str | None]:
    return {
        "git_sha": _env_value("EMAILDJ_GIT_SHA", "GITHUB_SHA") or _git_sha_from_repo(),
        "build_id": _env_value("EMAILDJ_BUILD_ID", "BUILD_ID"),
        "image_tag": _env_value("EMAILDJ_IMAGE_TAG", "IMAGE_TAG"),
        "release_version": _env_value("EMAILDJ_RELEASE_VERSION"),
    }


def _release_fingerprint(fields: dict[str, str | None]) -> str | None:
    ordered = ["git_sha", "build_id", "image_tag", "release_version"]
    parts = [f"{name}={fields[name]}" for name in ordered if fields.get(name)]
    return "|".join(parts) if parts else None


def _chrome_extension_origin_state(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return "unset"
    if value == "chrome-extension://dev":
        return "default_dev_placeholder"
    return "explicit_pinned"


def _web_app_origin_state(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return "unset"
    origins = [part.strip() for part in value.split(",") if part.strip()]
    if not origins:
        return "unset"
    if all((urlparse(origin).hostname or "").strip().lower() in _LOCAL_WEB_ORIGIN_HOSTS for origin in origins):
        return "default_dev_placeholder"
    return "explicit_pinned"


def _beta_keys_state(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        return "unset"
    keys = {part.strip() for part in value.split(",") if part.strip()}
    if "dev-beta-key" in keys:
        return "default_dev_placeholder"
    return "explicit_pinned"


def _rate_limit_value() -> int:
    raw = (os.environ.get("EMAILDJ_WEB_RATE_LIMIT_PER_MIN") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return 30
    return max(value, 1)


def validate_runtime_debug_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError("runtime debug payload must be a JSON object")

    missing_critical: list[str] = []
    for field in _RUNTIME_DEBUG_REQUIRED_FIELDS:
        if field not in payload:
            missing_critical.append(field)

    route_gates = payload.get("route_gates")
    if not isinstance(route_gates, dict) or "preview" not in route_gates:
        missing_critical.append("route_gates.preview")

    if not any(field in payload for field in _RELEASE_IDENTITY_KEYS):
        missing_critical.append("release_identity_fields")

    missing_recommended: list[str] = []
    for field in _RUNTIME_DEBUG_RECOMMENDED_FIELDS:
        if field not in payload:
            missing_recommended.append(field)

    route_gate_sources = payload.get("route_gate_sources")
    if not isinstance(route_gate_sources, dict) or "preview" not in route_gate_sources:
        missing_recommended.append("route_gate_sources.preview")

    release_identity_present = any(field in payload for field in _RELEASE_IDENTITY_KEYS)
    release_identity_populated = any(str(payload.get(field) or "").strip() for field in _RELEASE_IDENTITY_KEYS)

    return {
        "missing_critical": missing_critical,
        "missing_recommended": missing_recommended,
        "release_identity_present": release_identity_present,
        "release_identity_populated": release_identity_populated,
    }


def build_runtime_debug_payload() -> dict[str, Any]:
    policies = resolve_runtime_policies()
    release_fields = _release_fingerprint_fields()
    release_fingerprint = _release_fingerprint(release_fields)

    chrome_extension_origin = (os.environ.get("CHROME_EXTENSION_ORIGIN") or "").strip()
    web_app_origin = (os.environ.get("WEB_APP_ORIGIN") or "").strip()
    beta_keys = (os.environ.get("EMAILDJ_WEB_BETA_KEYS") or "").strip()
    configured_quick_generate_mode = (os.environ.get("EMAILDJ_QUICK_GENERATE_MODE") or "").strip().lower() or None

    if policies.provider_stub_enabled:
        effective_provider_source = "provider_stub"
        effective_provider = "provider_stub"
        effective_model = "mock"
    else:
        resolved_model = get_model(tier=2, task="web_mvp")
        effective_provider_source = "external_provider"
        effective_provider = resolved_model.provider
        effective_model = resolved_model.model_name

    return {
        "app_env": policies.app_env,
        "runtime_mode": policies.quick_generate_mode,
        "quick_generate_mode": policies.quick_generate_mode,
        "provider_stub_enabled": policies.provider_stub_enabled,
        "real_provider_preference": policies.real_provider_preference,
        "launch_mode": policies.launch_mode,
        "route_gates": dict(policies.route_gates),
        "route_gate_sources": dict(policies.route_gate_sources),
        "preview_pipeline_enabled": policies.preview_pipeline_enabled,
        "generated_at_utc": _utc_now_text(),
        "configured_quick_generate_mode": configured_quick_generate_mode,
        "effective_quick_generate_mode": policies.quick_generate_mode,
        "effective_provider_source": effective_provider_source,
        "effective_provider": effective_provider,
        "effective_model": effective_model,
        "effective_model_identifier": f"{effective_provider}/{effective_model}",
        "release_fingerprint": release_fingerprint,
        "release_fingerprint_available": bool(release_fingerprint),
        **release_fields,
        "chrome_extension_origin": chrome_extension_origin or None,
        "chrome_extension_origin_state": _chrome_extension_origin_state(chrome_extension_origin),
        "web_app_origin": web_app_origin or None,
        "web_app_origin_state": _web_app_origin_state(web_app_origin),
        "beta_keys_state": _beta_keys_state(beta_keys),
        "web_rate_limit_per_min": _rate_limit_value(),
        "web_rate_limit_source": "explicit_env" if "EMAILDJ_WEB_RATE_LIMIT_PER_MIN" in os.environ else "middleware_default_30",
    }
