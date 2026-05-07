#!/usr/bin/env python3
"""Inspect the deployed web-app bundle for launch-critical client config."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from html.parser import HTMLParser
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TIMEOUT_SECONDS = 15.0
LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}
LOCAL_HUB_URLS = {
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://0.0.0.0:8000",
    "http://[::1]:8000",
}
LAUNCH_BLOCKER_NOTE = (
    "Web-app bundle probing checks static client configuration only. It does not clear deployed Hub API smoke, runtime "
    "snapshot, origin pinning, beta-key, or durable infra blockers."
)


@dataclass
class FetchResult:
    url: str
    status_code: int | None
    text: str
    content_type: str | None = None
    error: str | None = None


class _AssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        candidate = ""
        if tag.lower() == "script":
            candidate = attr_map.get("src", "")
        elif tag.lower() == "link":
            candidate = attr_map.get("href", "")
        if candidate and re.search(r"\.(?:js|mjs|css)(?:\?|$)", candidate):
            self.assets.append(candidate)


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - probe artifacts should fail closed into empty context
        return {}
    return payload if isinstance(payload, dict) else {}


def _git_head_sha() -> str | None:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    return completed.stdout.strip() or None


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _origin_from_url(raw_url: str | None) -> str | None:
    parsed = urlparse(str(raw_url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _web_app_url_from_discovery() -> str | None:
    payload = _read_json(ROOT / "reports" / "launch" / "deployment_discovery.json")
    if not payload.get("usable_as_web_app_origin_candidate"):
        return None
    origin = _origin_from_url(payload.get("candidate_web_app_origin"))
    return origin


def _fetch_text(url: str, *, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> FetchResult:
    request = Request(url, headers={"User-Agent": "EmailDJLaunchProbe/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - operator-supplied launch URL probe
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            text = raw.decode(charset, errors="replace")
            return FetchResult(
                url=response.geturl(),
                status_code=getattr(response, "status", None),
                text=text,
                content_type=response.headers.get("content-type"),
            )
    except HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return FetchResult(url=url, status_code=exc.code, text=text, error=f"http_error:{exc.code}")
    except URLError as exc:
        return FetchResult(url=url, status_code=None, text="", error=f"url_error:{exc.reason}")
    except Exception as exc:  # noqa: BLE001 - serialize all network probe failures
        return FetchResult(url=url, status_code=None, text="", error=f"{type(exc).__name__}:{exc}")


def _asset_urls(index_html: str, *, base_url: str) -> list[str]:
    parser = _AssetParser()
    parser.feed(index_html)
    urls = [urljoin(base_url, asset) for asset in parser.assets]
    return list(dict.fromkeys(urls))


def _decode_js_string(raw_value: str) -> str:
    try:
        return json.loads(f'"{raw_value}"')
    except Exception:  # noqa: BLE001
        return raw_value.replace("\\/", "/")


def _extract_vite_env_literal(built_text: str, key: str) -> str | None:
    pattern = re.compile(
        rf'(?:^|[{{,\s])(?:"{re.escape(key)}"|{re.escape(key)})\s*:\s*(["\'])(?P<value>(?:\\.|(?!\1).)*?)\1'
    )
    match = pattern.search(built_text)
    if not match:
        return None
    return _decode_js_string(match.group("value"))


def _hub_url_finding(value: str | None) -> str | None:
    if not value:
        return "vite_hub_url_not_found_in_bundle"
    parsed = urlparse(value.strip())
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme != "https" or not parsed.netloc:
        return "vite_hub_url_not_deployed_https"
    if host in LOCAL_HOSTS or host.endswith(".local"):
        return "vite_hub_url_not_deployed_https"
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        return "vite_hub_url_not_root"
    return None


def _preview_finding(value: str | None) -> str | None:
    if not value:
        return "vite_preview_pipeline_not_found_in_bundle"
    if value.strip().lower() not in {"on", "off", "true", "false", "1", "0"}:
        return "vite_preview_pipeline_invalid"
    return None


def _auth_gate_findings(result: FetchResult, *, origin: str) -> list[str]:
    if result.status_code != 401:
        return []
    findings = ["web_app_deployment_requires_auth"]
    host = (urlparse(origin).hostname or "").lower()
    if host.endswith(".vercel.app"):
        findings.append("web_app_deployment_requires_auth_or_vercel_protection_bypass")
    return findings


def inspect_web_app_deployment(
    web_app_url: str | None,
    *,
    source_git_sha: str | None = None,
    workspace_git_sha: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    fetcher: Callable[..., FetchResult] = _fetch_text,
) -> dict:
    origin = _origin_from_url(web_app_url)
    failures: list[str] = []
    warnings: list[str] = []
    asset_results: list[dict] = []
    index_result: FetchResult | None = None
    built_text = ""

    if not origin:
        failures.append("web_app_url_missing_or_invalid")
        return {
            "generated_at": _utc_now_text(),
            "web_app_url": web_app_url,
            "normalized_web_app_origin": None,
            "source_git_sha": source_git_sha,
            "workspace_git_sha_at_probe": workspace_git_sha,
            "probe_matches_workspace_head": bool(source_git_sha and workspace_git_sha and source_git_sha == workspace_git_sha),
            "client_bundle_usable": False,
            "failures": failures,
            "warnings": warnings,
            "clears_launch_blockers": False,
            "launch_blocker_note": LAUNCH_BLOCKER_NOTE,
        }

    index_result = fetcher(origin + "/", timeout_seconds=timeout_seconds)
    if source_git_sha and workspace_git_sha and source_git_sha != workspace_git_sha:
        failures.append("deployment_discovery_sha_mismatch_with_workspace_head")
    if index_result.error or not index_result.status_code or index_result.status_code >= 400:
        failures.append(index_result.error or f"index_fetch_http_{index_result.status_code}")
        failures.extend(_auth_gate_findings(index_result, origin=origin))
    built_text += index_result.text or ""

    assets = _asset_urls(index_result.text or "", base_url=index_result.url or origin + "/")
    same_origin_assets = [asset for asset in assets if _origin_from_url(asset) == origin]
    if not same_origin_assets:
        failures.append("no_same_origin_bundle_assets_found")
    for asset_url in same_origin_assets[:30]:
        asset_result = fetcher(asset_url, timeout_seconds=timeout_seconds)
        asset_results.append(
            {
                "url": asset_result.url,
                "status_code": asset_result.status_code,
                "content_type": asset_result.content_type,
                "error": asset_result.error,
            }
        )
        if asset_result.error or not asset_result.status_code or asset_result.status_code >= 400:
            failures.append(f"asset_fetch_failed:{asset_url}")
            continue
        built_text += "\n" + asset_result.text

    hub_url = _extract_vite_env_literal(built_text, "VITE_HUB_URL")
    preview_pipeline = _extract_vite_env_literal(built_text, "VITE_PRESET_PREVIEW_PIPELINE")
    hub_finding = _hub_url_finding(hub_url)
    preview_finding = _preview_finding(preview_pipeline)
    if hub_finding:
        failures.append(hub_finding)
    if preview_finding:
        failures.append(preview_finding)
    if "Missing VITE_HUB_URL for a production web-app build" in built_text and not hub_url:
        warnings.append("missing_hub_url_runtime_error_present")
    if any(value in built_text for value in LOCAL_HUB_URLS):
        warnings.append("local_dev_hub_url_string_present_in_bundle")

    failures = list(dict.fromkeys(failures))
    warnings = list(dict.fromkeys(warnings))
    return {
        "generated_at": _utc_now_text(),
        "web_app_url": web_app_url,
        "normalized_web_app_origin": origin,
        "source_git_sha": source_git_sha,
        "workspace_git_sha_at_probe": workspace_git_sha,
        "probe_matches_workspace_head": bool(source_git_sha and workspace_git_sha and source_git_sha == workspace_git_sha),
        "index": {
            "url": index_result.url if index_result else origin + "/",
            "status_code": index_result.status_code if index_result else None,
            "content_type": index_result.content_type if index_result else None,
            "error": index_result.error if index_result else "not_fetched",
        },
        "asset_count": len(same_origin_assets),
        "assets_checked": asset_results,
        "detected_vite_hub_url": hub_url,
        "detected_preview_pipeline": preview_pipeline,
        "client_bundle_usable": not failures,
        "failures": failures,
        "warnings": warnings,
        "clears_launch_blockers": False,
        "launch_blocker_note": LAUNCH_BLOCKER_NOTE,
    }


def _write_markdown(path: Path, payload: dict) -> None:
    lines = [
        "# Web App Deployment Probe",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Web app URL: `{payload.get('web_app_url') or 'unset'}`",
        f"- Normalized origin: `{payload.get('normalized_web_app_origin') or 'unset'}`",
        f"- Source git SHA: `{payload.get('source_git_sha') or 'unset'}`",
        f"- Workspace git SHA at probe: `{payload.get('workspace_git_sha_at_probe') or 'unset'}`",
        f"- Probe matches workspace HEAD: `{payload.get('probe_matches_workspace_head')}`",
        f"- Client bundle usable: `{payload.get('client_bundle_usable')}`",
        f"- Detected VITE_HUB_URL: `{payload.get('detected_vite_hub_url') or 'none'}`",
        f"- Detected VITE_PRESET_PREVIEW_PIPELINE: `{payload.get('detected_preview_pipeline') or 'none'}`",
        f"- Clears launch blockers: `{payload.get('clears_launch_blockers')}`",
        f"- Launch blocker note: {payload.get('launch_blocker_note')}",
        "",
        "## Failures",
        "",
    ]
    failures = payload.get("failures") or []
    if failures:
        for failure in failures:
            lines.append(f"- `{failure}`")
    else:
        lines.append("- None")

    warnings = payload.get("warnings") or []
    lines.extend(["", "## Warnings", ""])
    if warnings:
        for warning in warnings:
            lines.append(f"- `{warning}`")
    else:
        lines.append("- None")

    assets = payload.get("assets_checked") or []
    lines.extend(["", "## Assets Checked", ""])
    if assets:
        for asset in assets:
            lines.append(
                f"- `{asset.get('url')}` status=`{asset.get('status_code')}` content_type=`{asset.get('content_type')}` error=`{asset.get('error') or 'none'}`"
            )
    else:
        lines.append("- None")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_probe(*, web_app_url: str | None = None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> tuple[Path, Path, dict]:
    discovery = _read_json(ROOT / "reports" / "launch" / "deployment_discovery.json")
    target_url = web_app_url or _web_app_url_from_discovery()
    payload = inspect_web_app_deployment(
        target_url,
        source_git_sha=discovery.get("current_git_sha") if discovery else None,
        workspace_git_sha=_git_head_sha(),
        timeout_seconds=timeout_seconds,
    )
    report_dir = ROOT / "reports" / "launch"
    json_path = report_dir / "web_app_deployment_probe.json"
    md_path = report_dir / "web_app_deployment_probe.md"
    _write_json(json_path, payload)
    _write_markdown(md_path, payload)
    return json_path, md_path, payload


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe deployed web-app static bundle launch config.")
    parser.add_argument("--url", default="", help="Deployed web-app origin. Defaults to deployment_discovery candidate.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"HTTP timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS}).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    json_path, md_path, payload = write_probe(web_app_url=args.url or None, timeout_seconds=args.timeout_seconds)
    print(
        json.dumps(
            {
                "web_app_deployment_probe_json": str(json_path),
                "web_app_deployment_probe_md": str(md_path),
                "client_bundle_usable": payload.get("client_bundle_usable"),
                "detected_vite_hub_url": payload.get("detected_vite_hub_url"),
                "detected_preview_pipeline": payload.get("detected_preview_pipeline"),
                "failures": payload.get("failures"),
            },
            indent=2,
        )
    )
    return 0 if payload.get("client_bundle_usable") else 1


if __name__ == "__main__":
    raise SystemExit(main())
