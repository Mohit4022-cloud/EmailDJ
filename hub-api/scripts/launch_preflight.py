#!/usr/bin/env python3
"""Validate operator inputs and provider transport before launch verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional in some environments
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


DEFAULT_TIMEOUT_SECONDS = 15.0
_REQUIRED_INPUTS = ("STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY")
_PROVIDER_PROBE_URLS = {
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
_DEV_BETA_KEYS = {"dev-beta-key"}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_launch_env() -> dict[str, dict[str, bool]]:
    explicit_operator_inputs = {
        name: bool((os.environ.get(name) or "").strip())
        for name in _REQUIRED_INPUTS
    }
    load_dotenv(dotenv_path=ROOT / ".env", override=False)
    source_state: dict[str, dict[str, bool]] = {}
    for name, was_explicit in explicit_operator_inputs.items():
        value_after_dotenv = bool((os.environ.get(name) or "").strip())
        dotenv_value_ignored = bool(value_after_dotenv and not was_explicit)
        if dotenv_value_ignored:
            os.environ.pop(name, None)
        source_state[name] = {
            "explicit_env_present": was_explicit,
            "dotenv_value_present": dotenv_value_ignored,
            "dotenv_value_ignored": dotenv_value_ignored,
            "effective_present": bool((os.environ.get(name) or "").strip()),
        }
    return source_state


def _required_provider_env() -> tuple[str, str]:
    provider = (os.environ.get("EMAILDJ_REAL_PROVIDER") or "openai").strip().lower() or "openai"
    key_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
    }.get(provider, "OPENAI_API_KEY")
    return provider, key_name


def _provider_probe(provider: str, provider_env: str) -> tuple[str, dict[str, str]]:
    probe_url = _PROVIDER_PROBE_URLS.get(provider, _PROVIDER_PROBE_URLS["openai"])
    headers: dict[str, str] = {}
    key_value = (os.environ.get(provider_env) or "").strip()
    if provider == "anthropic":
        headers["x-api-key"] = key_value
        headers["anthropic-version"] = "2023-06-01"
    else:
        headers["Authorization"] = f"Bearer {key_value}"
    return probe_url, headers


def _operator_input_step(name: str) -> str:
    if name == "STAGING_BASE_URL":
        return "Set `STAGING_BASE_URL` to the staging hub-api root URL (for example `https://hub-staging.example.com`) before running launch verification."
    if name == "PROD_BASE_URL":
        return "Set `PROD_BASE_URL` to the production hub-api root URL (for example `https://hub.example.com`) before running launch verification."
    if name == "BETA_KEY":
        return "Set `BETA_KEY` to one exact non-dev deployed `EMAILDJ_WEB_BETA_KEYS` value before running launch verification."
    return f"Set `{name}` before running launch verification."


def _deployment_discovery_context() -> dict[str, Any]:
    path = ROOT / "reports" / "launch" / "deployment_discovery.json"
    context: dict[str, Any] = {
        "path": str(path),
        "state": "missing",
        "found": False,
        "candidate_web_app_origin": None,
        "usable_as_web_app_origin_candidate": False,
        "clears_launch_blockers": False,
        "operator_note": None,
    }
    if not path.exists():
        return context
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - preflight should serialize report context, not crash on it
        context["state"] = "malformed"
        context["operator_note"] = f"Could not read deployment discovery artifact: {exc}"
        return context
    candidate = payload.get("candidate_web_app_origin") if payload.get("usable_as_web_app_origin_candidate") else None
    context.update(
        {
            "state": "present",
            "found": bool(payload.get("found")),
            "candidate_web_app_origin": candidate,
            "usable_as_web_app_origin_candidate": bool(payload.get("usable_as_web_app_origin_candidate")),
            "clears_launch_blockers": bool(payload.get("clears_launch_blockers")),
            "operator_note": (
                "Candidate is for WEB_APP_ORIGIN only. It is a frontend origin, not a STAGING_BASE_URL or PROD_BASE_URL."
                if candidate
                else payload.get("launch_blocker_note")
            ),
        }
    )
    return context


def _normalize_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    path = parsed.path.rstrip("/")
    return parsed._replace(path=path, params="", query="", fragment="").geturl().rstrip("/")


def _validate_base_url(name: str, raw_url: str) -> list[str]:
    errors: list[str] = []
    parsed = urlparse(raw_url.strip())
    host = (parsed.hostname or "").strip().lower()
    path = (parsed.path or "").strip()
    if parsed.scheme != "https":
        errors.append(f"{name}:must_use_https")
    if not parsed.netloc or not host:
        errors.append(f"{name}:invalid_url")
        return errors
    if host in _LOCAL_HOSTS or host.endswith(".local"):
        errors.append(f"{name}:must_not_be_localhost")
    if path not in {"", "/"}:
        errors.append(f"{name}:must_be_hub_api_root_url")
    if parsed.params or parsed.query or parsed.fragment:
        errors.append(f"{name}:must_not_include_query_or_fragment")
    return errors


def _validate_operator_inputs() -> list[str]:
    errors: list[str] = []
    staging_url = (os.environ.get("STAGING_BASE_URL") or "").strip()
    prod_url = (os.environ.get("PROD_BASE_URL") or "").strip()
    beta_key = (os.environ.get("BETA_KEY") or "").strip()
    errors.extend(_validate_base_url("STAGING_BASE_URL", staging_url))
    errors.extend(_validate_base_url("PROD_BASE_URL", prod_url))
    if staging_url and prod_url and _normalize_url(staging_url) == _normalize_url(prod_url):
        errors.append("STAGING_BASE_URL:must_differ_from_PROD_BASE_URL")
    if beta_key in _DEV_BETA_KEYS:
        errors.append("BETA_KEY:must_not_be_dev_placeholder")
    return errors


def _invalid_operator_input_steps(errors: list[str]) -> list[str]:
    steps: list[str] = []
    if any(error.startswith("STAGING_BASE_URL:") for error in errors):
        steps.append("Set `STAGING_BASE_URL` to the deployed staging hub-api root URL using HTTPS, with no path, query, or localhost host.")
    if any(error.startswith("PROD_BASE_URL:") for error in errors):
        steps.append("Set `PROD_BASE_URL` to the deployed production hub-api root URL using HTTPS, with no path, query, or localhost host.")
    if "STAGING_BASE_URL:must_differ_from_PROD_BASE_URL" in errors:
        steps.append("Use distinct staging and production hub-api roots; launch verification must prove both environments separately.")
    if any(error.startswith("BETA_KEY:") for error in errors):
        steps.append("Set `BETA_KEY` to a non-dev deployed beta key that exactly matches one `EMAILDJ_WEB_BETA_KEYS` value.")
    return list(dict.fromkeys(steps))


def _report_paths() -> tuple[Path, Path]:
    report_dir = ROOT / "reports" / "launch"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / "preflight.json", report_dir / "preflight.md"


def run_launch_preflight(*, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    operator_input_sources = _load_launch_env()
    deployment_discovery = _deployment_discovery_context()
    provider, provider_env = _required_provider_env()
    presence = {name: bool((os.environ.get(name) or "").strip()) for name in (*_REQUIRED_INPUTS, provider_env)}
    missing_inputs = [name for name, present in presence.items() if not present]
    operator_input_errors = [] if missing_inputs else _validate_operator_inputs()

    result: dict[str, Any] = {
        "generated_at": _utc_now_text(),
        "ready": False,
        "failure_bucket": None,
        "provider": provider,
        "provider_env": provider_env,
        "timeout_seconds": timeout_seconds,
        "required_inputs_present": presence,
        "operator_input_sources": operator_input_sources,
        "missing_inputs": missing_inputs,
        "operator_input_errors": operator_input_errors,
        "transport_checked": False,
        "transport_ok": None,
        "probe_url": None,
        "probe_status_code": None,
        "transport_error_type": None,
        "transport_error": None,
        "deployment_discovery": deployment_discovery,
        "next_steps": [],
    }
    if missing_inputs:
        result["failure_bucket"] = "operator_input_missing"
        result["next_steps"] = [_operator_input_step(name) for name in missing_inputs]
        candidate = deployment_discovery.get("candidate_web_app_origin")
        if candidate:
            result["next_steps"].append(
                f"Use discovered web-app candidate `{candidate}` only for `WEB_APP_ORIGIN`; do not use it for `STAGING_BASE_URL` or `PROD_BASE_URL`."
            )
        return result
    if operator_input_errors:
        result["failure_bucket"] = "operator_input_invalid"
        result["next_steps"] = _invalid_operator_input_steps(operator_input_errors)
        return result

    probe_url, headers = _provider_probe(provider, provider_env)
    result["probe_url"] = probe_url
    result["transport_checked"] = True
    try:
        response = httpx.get(probe_url, headers=headers, timeout=timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - preflight should serialize transport failures cleanly
        result["failure_bucket"] = "transport_or_provider"
        result["transport_ok"] = False
        result["transport_error_type"] = type(exc).__name__
        result["transport_error"] = str(exc)
        result["next_steps"] = [
            "Restore outbound DNS/HTTPS access from the operator host to the configured provider before rerunning launch verification.",
        ]
        return result

    result["probe_status_code"] = response.status_code
    result["transport_ok"] = True
    if response.status_code >= 400:
        result["failure_bucket"] = "transport_or_provider"
        result["next_steps"] = [
            f"Provider probe reached the upstream service but returned HTTP {response.status_code}. Fix provider credentials or upstream availability before rerunning launch verification.",
        ]
        return result

    result["ready"] = True
    result["next_steps"] = [
        "Launch preflight passed. Proceed with hub-api runtime snapshot capture and real-provider verification from this host.",
    ]
    return result


def _write_report(result: dict[str, Any]) -> tuple[Path, Path]:
    json_path, md_path = _report_paths()
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    lines = [
        "# Launch Preflight",
        "",
        f"- Generated at: `{result['generated_at']}`",
        f"- Ready: `{result['ready']}`",
        f"- Failure bucket: `{result.get('failure_bucket') or 'none'}`",
        f"- Provider: `{result['provider']}`",
        f"- Provider env: `{result['provider_env']}`",
        f"- Timeout seconds: `{result['timeout_seconds']}`",
        "",
        "> `STAGING_BASE_URL` and `PROD_BASE_URL` must be HTTPS hub-api root URLs, not frontend URLs. `BETA_KEY` must match one non-dev deployed `EMAILDJ_WEB_BETA_KEYS` value.",
        "",
        "## Required Inputs",
        "",
    ]
    for name, present in dict(result.get("required_inputs_present") or {}).items():
        lines.append(f"- `{name}` present=`{present}`")

    input_errors = list(result.get("operator_input_errors") or [])
    if input_errors:
        lines.extend(["", "## Operator Input Validation", ""])
        for error in input_errors:
            lines.append(f"- `{error}`")

    operator_sources = dict(result.get("operator_input_sources") or {})
    if operator_sources:
        lines.extend(["", "## Operator Input Sources", ""])
        for name, source in operator_sources.items():
            lines.append(
                f"- `{name}` explicit_env_present=`{source.get('explicit_env_present')}` "
                f"dotenv_value_present=`{source.get('dotenv_value_present')}` "
                f"dotenv_value_ignored=`{source.get('dotenv_value_ignored')}` "
                f"effective_present=`{source.get('effective_present')}`"
            )

    deployment_discovery = dict(result.get("deployment_discovery") or {})
    lines.extend(["", "## Deployment Discovery Context", ""])
    lines.append(f"- `state`: `{deployment_discovery.get('state') or 'missing'}`")
    lines.append(f"- `candidate_web_app_origin`: `{deployment_discovery.get('candidate_web_app_origin') or 'none'}`")
    lines.append(
        f"- `usable_as_web_app_origin_candidate`: `{deployment_discovery.get('usable_as_web_app_origin_candidate')}`"
    )
    lines.append(f"- `clears_launch_blockers`: `{deployment_discovery.get('clears_launch_blockers')}`")
    if deployment_discovery.get("operator_note"):
        lines.append(f"- `operator_note`: {deployment_discovery.get('operator_note')}")

    lines.extend(
        [
            "",
            "## Transport Probe",
            "",
            f"- `transport_checked`: `{result.get('transport_checked')}`",
            f"- `transport_ok`: `{result.get('transport_ok')}`",
            f"- `probe_url`: `{result.get('probe_url') or 'unset'}`",
            f"- `probe_status_code`: `{result.get('probe_status_code') if result.get('probe_status_code') is not None else 'n/a'}`",
        ]
    )
    if result.get("transport_error_type"):
        lines.append(f"- `transport_error_type`: `{result['transport_error_type']}`")
    if result.get("transport_error"):
        lines.append(f"- `transport_error`: `{result['transport_error']}`")

    lines.extend(["", "## Next Steps", ""])
    steps = list(result.get("next_steps") or [])
    if steps:
        for step in steps:
            lines.append(f"- {step}")
    else:
        lines.append("- None")

    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check operator inputs and provider transport before launch verification.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Provider probe timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    result = run_launch_preflight(timeout_seconds=args.timeout_seconds)
    json_path, md_path = _write_report(result)
    print(
        json.dumps(
            {
                "preflight_json": str(json_path),
                "preflight_md": str(md_path),
                "ready": result["ready"],
                "failure_bucket": result.get("failure_bucket"),
            },
            indent=2,
        )
    )
    return 0 if result["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
