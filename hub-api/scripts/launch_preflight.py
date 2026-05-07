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


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_launch_env() -> None:
    explicit_operator_inputs = {name: name in os.environ for name in _REQUIRED_INPUTS}
    load_dotenv(dotenv_path=ROOT / ".env", override=False)
    for name, was_explicit in explicit_operator_inputs.items():
        if not was_explicit:
            os.environ.pop(name, None)


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
        return "Set `BETA_KEY` to one exact deployed `EMAILDJ_WEB_BETA_KEYS` value before running launch verification."
    return f"Set `{name}` before running launch verification."


def _report_paths() -> tuple[Path, Path]:
    report_dir = ROOT / "reports" / "launch"
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir / "preflight.json", report_dir / "preflight.md"


def run_launch_preflight(*, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    _load_launch_env()
    provider, provider_env = _required_provider_env()
    presence = {name: bool((os.environ.get(name) or "").strip()) for name in (*_REQUIRED_INPUTS, provider_env)}
    missing_inputs = [name for name, present in presence.items() if not present]

    result: dict[str, Any] = {
        "generated_at": _utc_now_text(),
        "ready": False,
        "failure_bucket": None,
        "provider": provider,
        "provider_env": provider_env,
        "timeout_seconds": timeout_seconds,
        "required_inputs_present": presence,
        "missing_inputs": missing_inputs,
        "transport_checked": False,
        "transport_ok": None,
        "probe_url": None,
        "probe_status_code": None,
        "transport_error_type": None,
        "transport_error": None,
        "next_steps": [],
    }
    if missing_inputs:
        result["failure_bucket"] = "operator_input_missing"
        result["next_steps"] = [_operator_input_step(name) for name in missing_inputs]
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
        "> `STAGING_BASE_URL` and `PROD_BASE_URL` must be hub-api root URLs, not frontend URLs. `BETA_KEY` must match one deployed `EMAILDJ_WEB_BETA_KEYS` value.",
        "",
        "## Required Inputs",
        "",
    ]
    for name, present in dict(result.get("required_inputs_present") or {}).items():
        lines.append(f"- `{name}` present=`{present}`")

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
