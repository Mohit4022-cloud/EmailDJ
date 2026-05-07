#!/usr/bin/env python3
"""Generate the operator handoff needed to clear launch blockers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _blocked_ids(audit: dict[str, Any]) -> set[str]:
    return {str(item.get("id")) for item in audit.get("items") or [] if item.get("status") == "blocked"}


def _audit_blockers(audit: dict[str, Any]) -> list[dict[str, Any]]:
    blockers = []
    for item in audit.get("items") or []:
        if item.get("status") != "blocked":
            continue
        blockers.append(
            {
                "id": item.get("id"),
                "requirement": item.get("requirement"),
                "blockers": list(item.get("blockers") or []),
            }
        )
    return blockers


def _provider_env_for(provider: str) -> str:
    mapping = {
        "anthropic": "ANTHROPIC_API_KEY",
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    return mapping.get(provider, "OPENAI_API_KEY")


def _md_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def build_launch_handoff() -> dict[str, Any]:
    audit = _read_json(ROOT / "reports" / "launch" / "completion_audit.json")
    latest = _read_json(ROOT / "reports" / "launch" / "latest.json")
    preflight = _read_json(ROOT / "reports" / "launch" / "preflight.json")
    blocked = _blocked_ids(audit)
    missing_inputs = set(preflight.get("missing_inputs") or [])
    preflight_needs_inputs = preflight.get("ready") is not True
    provider = (
        preflight.get("provider")
        or latest.get("effective_provider")
        or latest.get("real_provider_preference")
        or "openai"
    )
    provider = str(provider).strip().lower() or "openai"
    provider_env = str(preflight.get("provider_env") or _provider_env_for(provider))
    launch_mode = str(latest.get("launch_mode") or "limited_rollout")

    required_exports = [
        {
            "name": "STAGING_BASE_URL",
            "value": "https://<staging-hub-api-root>",
            "required_when": (
                "deployed_preflight_inputs" in blocked
                or "STAGING_BASE_URL" in missing_inputs
                or preflight_needs_inputs
            ),
            "note": "Must be the staging Hub API root URL, not the web-app URL.",
        },
        {
            "name": "PROD_BASE_URL",
            "value": "https://<prod-hub-api-root>",
            "required_when": (
                "deployed_preflight_inputs" in blocked
                or "PROD_BASE_URL" in missing_inputs
                or preflight_needs_inputs
            ),
            "note": "Must be the production Hub API root URL and must differ from staging.",
        },
        {
            "name": "BETA_KEY",
            "value": "<one-non-dev-beta-key-from-EMAILDJ_WEB_BETA_KEYS>",
            "required_when": (
                "deployed_preflight_inputs" in blocked
                or "BETA_KEY" in missing_inputs
                or preflight_needs_inputs
            ),
            "note": "Must be exported explicitly in the shell; .env values are intentionally ignored.",
        },
        {
            "name": "EMAILDJ_EXPECTED_HUB_URL",
            "value": "$STAGING_BASE_URL",
            "required_when": "deployed_http_smoke" in blocked or "runtime_snapshots" in blocked,
            "note": "Used by release-bundle checks.",
        },
        {
            "name": "EMAILDJ_EXPECTED_BETA_KEY",
            "value": "$BETA_KEY",
            "required_when": "deployed_http_smoke" in blocked or "runtime_snapshots" in blocked,
            "note": "Used by extension release-bundle checks.",
        },
        {
            "name": "EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE",
            "value": "off",
            "required_when": True,
            "note": "Keep off for limited rollout unless preview is intentionally enabled.",
        },
        {
            "name": "VITE_HUB_URL",
            "value": "$STAGING_BASE_URL",
            "required_when": True,
            "note": "Build-time Hub API root for web-app and extension release verification.",
        },
        {
            "name": "VITE_EMAILDJ_BETA_KEY",
            "value": "$BETA_KEY",
            "required_when": True,
            "note": "Build-time beta key for extension release verification.",
        },
        {
            "name": "VITE_PRESET_PREVIEW_PIPELINE",
            "value": "off",
            "required_when": True,
            "note": "Build-time preview-pipeline flag for web-app release verification.",
        },
    ]

    dashboard_inputs = [
        {
            "name": "EMAILDJ_LAUNCH_MODE",
            "value": launch_mode,
            "required_when": True,
        },
        {
            "name": "EMAILDJ_REAL_PROVIDER",
            "value": provider,
            "required_when": True,
        },
        {
            "name": provider_env,
            "value": f"<{provider}-api-key>",
            "required_when": True,
        },
        {
            "name": "WEB_APP_ORIGIN",
            "value": "https://<deployed-web-app-origin>",
            "required_when": "pinned_origins_beta_provider" in blocked,
        },
        {
            "name": "CHROME_EXTENSION_ORIGIN",
            "value": "chrome-extension://<shipped-extension-id>",
            "required_when": "pinned_origins_beta_provider" in blocked or "chrome_extension_real_target" in blocked,
        },
        {
            "name": "EMAILDJ_WEB_BETA_KEYS",
            "value": "<non-dev-beta-key-1>,<non-dev-beta-key-2>",
            "required_when": "pinned_origins_beta_provider" in blocked,
        },
        {
            "name": "EMAILDJ_WEB_RATE_LIMIT_PER_MIN",
            "value": "300",
            "required_when": True,
        },
        {
            "name": "USE_PROVIDER_STUB",
            "value": "0",
            "required_when": True,
        },
        {
            "name": "REDIS_URL",
            "value": "<managed-redis-url>",
            "required_when": "durable_infra" in blocked,
        },
        {
            "name": "DATABASE_URL",
            "value": "<managed-postgres-url>",
            "required_when": "durable_infra" in blocked,
        },
        {
            "name": "VECTOR_STORE_BACKEND",
            "value": "pgvector",
            "required_when": "durable_infra" in blocked,
        },
        {
            "name": "REDIS_FORCE_INMEMORY",
            "value": "<unset or 0>",
            "required_when": "durable_infra" in blocked,
        },
    ]

    commands = [
        "make render-blueprint-check",
        "make launch-preflight",
        "make launch-verify-deployed",
        "make launch-audit",
    ]

    return {
        "generated_at": _utc_now_text(),
        "current_status": audit.get("final_status") or "unknown",
        "launch_recommendation": latest.get("final_recommendation") or "unknown",
        "preflight_ready": bool(preflight.get("ready")),
        "provider": provider,
        "provider_env": provider_env,
        "required_exports": required_exports,
        "dashboard_inputs": dashboard_inputs,
        "commands": commands,
        "open_blockers": _audit_blockers(audit),
        "source_artifacts": {
            "completion_audit": str(ROOT / "reports" / "launch" / "completion_audit.json"),
            "launch_report": str(ROOT / "reports" / "launch" / "latest.json"),
            "preflight": str(ROOT / "reports" / "launch" / "preflight.json"),
        },
    }


def _shell_exports(handoff: dict[str, Any]) -> list[str]:
    lines = []
    for item in handoff["required_exports"]:
        if not item.get("required_when"):
            continue
        value = item["value"]
        lines.append(f'export {item["name"]}="{value}"')
    return lines


def _write_markdown(path: Path, handoff: dict[str, Any]) -> None:
    lines = [
        "# Launch Operator Handoff",
        "",
        f"- Generated at: `{handoff['generated_at']}`",
        f"- Current completion status: `{handoff['current_status']}`",
        f"- Launch recommendation: `{handoff['launch_recommendation']}`",
        f"- Preflight ready: `{handoff['preflight_ready']}`",
        f"- Provider: `{handoff['provider']}`",
        f"- Provider env: `{handoff['provider_env']}`",
        "",
        "## Shell Exports",
        "",
        "```bash",
        *_shell_exports(handoff),
        "```",
        "",
        "## Render / Deployment Dashboard Inputs",
        "",
        "| Name | Value | Required now |",
        "|---|---|---|",
    ]
    for item in handoff["dashboard_inputs"]:
        lines.append(f"| `{_md_cell(item['name'])}` | `{_md_cell(item['value'])}` | `{bool(item['required_when'])}` |")

    lines.extend(["", "## Commands", "", "```bash", *handoff["commands"], "```", "", "## Open Blockers", ""])
    for blocker in handoff["open_blockers"]:
        values = ", ".join(f"`{value}`" for value in blocker["blockers"]) or "`none`"
        lines.append(f"- `{blocker['id']}`: {values}")

    lines.extend(["", "## Source Artifacts", ""])
    for key, value in handoff["source_artifacts"].items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_launch_handoff() -> tuple[Path, Path, dict[str, Any]]:
    handoff = build_launch_handoff()
    report_dir = ROOT / "reports" / "launch"
    json_path = report_dir / "operator_handoff.json"
    md_path = report_dir / "operator_handoff.md"
    _write_json(json_path, handoff)
    _write_markdown(md_path, handoff)
    return json_path, md_path, handoff


def main() -> int:
    json_path, md_path, handoff = write_launch_handoff()
    print(
        json.dumps(
            {
                "operator_handoff_json": str(json_path),
                "operator_handoff_md": str(md_path),
                "current_status": handoff["current_status"],
                "open_blocker_count": len(handoff["open_blockers"]),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
