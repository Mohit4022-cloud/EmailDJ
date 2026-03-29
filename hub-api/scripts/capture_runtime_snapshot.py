#!/usr/bin/env python3
"""Capture a validated /web/v1/debug/config snapshot for launch parity."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime_debug import validate_runtime_debug_payload

DEFAULT_BUCKET_KEY = "rollout-audit"
DEFAULT_ENDPOINT = "generate"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_OUTPUTS = {
    "staging": ROOT / "reports" / "launch" / "runtime_snapshots" / "staging.json",
    "production": ROOT / "reports" / "launch" / "runtime_snapshots" / "production.json",
}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a validated runtime snapshot from /web/v1/debug/config.")
    parser.add_argument("--url", required=True, help="Base host or full /web/v1/debug/config URL.")
    parser.add_argument("--label", required=True, help="Snapshot label, usually staging or production.")
    parser.add_argument("--output", default="", help="Optional output path. Defaults by label for staging/production.")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        help='Optional request header in "Name: Value" format. May be passed multiple times.',
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Request timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    return parser.parse_args()


def _resolve_output_path(label: str, output: str) -> Path:
    raw_output = output.strip()
    if raw_output:
        return Path(raw_output).resolve()
    normalized = label.strip().lower()
    default = DEFAULT_OUTPUTS.get(normalized)
    if default is None:
        raise ValueError(f"label '{label}' requires --output because only staging/production have default paths")
    return default


def _resolve_request_url(raw_url: str) -> str:
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid URL: {raw_url}")

    path = parsed.path.rstrip("/")
    if not path:
        path = "/web/v1/debug/config"
    elif not path.endswith("/web/v1/debug/config"):
        path = f"{path}/web/v1/debug/config"

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    params.setdefault("endpoint", DEFAULT_ENDPOINT)
    params.setdefault("bucket_key", DEFAULT_BUCKET_KEY)
    return urlunparse(parsed._replace(path=path, query=urlencode(params)))


def _parse_headers(raw_headers: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for header in raw_headers:
        name, sep, value = header.partition(":")
        if not sep or not name.strip():
            raise ValueError(f"invalid header format: {header!r}")
        headers[name.strip()] = value.strip()
    return headers


def _warning_messages(validation: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    missing_recommended = list(validation.get("missing_recommended") or [])
    if missing_recommended:
        warnings.append(f"missing recommended runtime fields: {', '.join(missing_recommended)}")
    if validation.get("release_identity_present") and not validation.get("release_identity_populated"):
        warnings.append("release identity fields are present but all values are empty")
    return warnings


def _capture_payload(
    *,
    url: str,
    headers: dict[str, str],
    timeout_seconds: float,
) -> tuple[dict[str, Any], str]:
    source_url = _resolve_request_url(url)
    try:
        response = httpx.get(source_url, headers=headers, timeout=timeout_seconds, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise RuntimeError(f"request_failed:{source_url}:{exc}") from exc

    if response.status_code != 200:
        raise RuntimeError(f"non_200_response:{response.status_code}:{source_url}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"invalid_json:{source_url}:{exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"invalid_json_object:{source_url}:payload_not_object")
    return payload, source_url


def capture_runtime_snapshot(
    *,
    url: str,
    label: str,
    output: str = "",
    headers: list[str] | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    target_path = _resolve_output_path(label, output)
    payload, source_url = _capture_payload(
        url=url,
        headers=_parse_headers(list(headers or [])),
        timeout_seconds=timeout_seconds,
    )
    validation = validate_runtime_debug_payload(payload)
    missing_critical = list(validation["missing_critical"])
    if missing_critical:
        raise RuntimeError(f"schema_incomplete:{', '.join(missing_critical)}")

    warnings = _warning_messages(validation)
    snapshot_payload = {
        "captured_at_utc": _utc_now_text(),
        "source_url": source_url,
        "label": label,
        **payload,
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(snapshot_payload, indent=2), encoding="utf-8")
    return {
        "output": str(target_path),
        "label": label,
        "source_url": source_url,
        "warnings": warnings,
    }


def main() -> int:
    args = _parse_args()
    try:
        result = capture_runtime_snapshot(
            url=args.url,
            label=args.label,
            output=args.output,
            headers=args.header,
            timeout_seconds=args.timeout_seconds,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    for warning in result["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
