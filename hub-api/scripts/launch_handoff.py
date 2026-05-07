#!/usr/bin/env python3
"""Generate the operator handoff needed to clear launch blockers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
VERCEL_BYPASS_ENV = "VERCEL_AUTOMATION_BYPASS_SECRET"
VERCEL_BYPASS_HEADER = "x-vercel-protection-bypass"


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


def _blocker_clearance_plan(blocked: set[str], *, provider_env: str) -> list[dict[str, str]]:
    plan: list[dict[str, str]] = []
    if "deployed_preflight_inputs" in blocked:
        plan.append(
            {
                "id": "deployed_preflight_inputs",
                "action": "Export STAGING_BASE_URL, PROD_BASE_URL, and BETA_KEY on the operator machine, then run make launch-preflight.",
                "evidence": "hub-api/reports/launch/preflight.json has ready=true and no missing_inputs.",
            }
        )
    if "runtime_snapshots" in blocked:
        plan.append(
            {
                "id": "runtime_snapshots",
                "action": (
                    "Run make launch-verify-deployed after the operator exports are set; it captures staging and production "
                    "runtime snapshots with the deployed beta key."
                ),
                "evidence": (
                    "hub-api/reports/launch/runtime_snapshots/staging.json and production.json exist and share comparable "
                    "release fingerprint fields."
                ),
            }
        )
    if "pinned_origins_beta_provider" in blocked:
        plan.append(
            {
                "id": "pinned_origins_beta_provider",
                "action": (
                    "Set WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, EMAILDJ_WEB_BETA_KEYS, EMAILDJ_REAL_PROVIDER, "
                    f"{provider_env}, USE_PROVIDER_STUB=0, and EMAILDJ_WEB_RATE_LIMIT_PER_MIN in the deployment dashboard."
                ),
                "evidence": (
                    "launch latest shows web_app_origin_state=explicit_pinned, chrome_extension_origin_state=explicit_pinned, "
                    "beta_keys_state=explicit_pinned, and effective_provider_source=external_provider."
                ),
            }
        )
    if "durable_infra" in blocked:
        plan.append(
            {
                "id": "durable_infra",
                "action": (
                    "Provision managed Redis and Postgres, set REDIS_URL and DATABASE_URL, set VECTOR_STORE_BACKEND=pgvector, "
                    "and keep REDIS_FORCE_INMEMORY unset or 0."
                ),
                "evidence": (
                    "launch latest shows redis_config_state=external_redis_configured, database_config_state=external_postgres_configured, "
                    "and vector_store_config_state=pgvector_configured."
                ),
            }
        )
    if "deployed_http_smoke" in blocked:
        plan.append(
            {
                "id": "deployed_http_smoke",
                "action": (
                    "Run make launch-verify-deployed against staging. Default limited rollout proves generate and remix; "
                    "use EMAILDJ_DEPLOYED_SMOKE_FLOWS=generate,remix,preview only when preview is intentionally enabled."
                ),
                "evidence": (
                    "hub-api/debug_runs/smoke/deployed/summary.json proves external_provider traffic and green required route coverage."
                ),
            }
        )
    if "release_fingerprint_parity" in blocked:
        plan.append(
            {
                "id": "release_fingerprint_parity",
                "action": "Capture both staging and production runtime snapshots from deployed services after release metadata is available.",
                "evidence": "launch latest has release_fingerprint_parity.runtime_source_used from deployed snapshots and non-empty comparison_fields.",
            }
        )
    if "chrome_extension_real_target" in blocked:
        plan.append(
            {
                "id": "chrome_extension_real_target",
                "action": "Set CHROME_EXTENSION_ORIGIN to the shipped chrome-extension://<extension-id> and verify the side-panel flow in Chrome.",
                "evidence": "launch latest shows chrome_extension_origin_state=explicit_pinned and the extension release config passes.",
            }
        )
    if "launch_report_recommendation" in blocked:
        plan.append(
            {
                "id": "launch_report_recommendation",
                "action": "After clearing the blocker groups above, rerun make launch-audit and make launch-handoff.",
                "evidence": "completion_audit.json final_status=complete and launch latest no longer says Not yet launch-ready.",
            }
        )
    return plan


def build_launch_handoff() -> dict[str, Any]:
    audit = _read_json(ROOT / "reports" / "launch" / "completion_audit.json")
    latest = _read_json(ROOT / "reports" / "launch" / "latest.json")
    preflight = _read_json(ROOT / "reports" / "launch" / "preflight.json")
    deployment_discovery_path = ROOT / "reports" / "launch" / "deployment_discovery.json"
    deployment_discovery = _read_json(deployment_discovery_path)
    web_app_probe_path = ROOT / "reports" / "launch" / "web_app_deployment_probe.json"
    web_app_probe = _read_json(web_app_probe_path)
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
    web_app_origin_candidate = None
    if deployment_discovery.get("usable_as_web_app_origin_candidate"):
        web_app_origin_candidate = deployment_discovery.get("candidate_web_app_origin")

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
            "name": VERCEL_BYPASS_ENV,
            "value": "<vercel-automation-bypass-secret>",
            "required_when": VERCEL_BYPASS_ENV in missing_inputs
            or "vercel_protection_bypass_secret_missing" in set(web_app_probe.get("failures") or []),
            "note": f"Required only when the Vercel web-app deployment is protected; sent as `{VERCEL_BYPASS_HEADER}`.",
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
            "candidate_value": web_app_origin_candidate,
            "note": (
                "Candidate was discovered from GitHub/Vercel deployment metadata; still operator-owned and must be pinned "
                "in the Hub API deployment dashboard."
                if web_app_origin_candidate
                else "Must be the intended deployed web-app origin."
            ),
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
        "make launch-probe-web-app",
        "make launch-audit",
        "make launch-handoff",
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
        "blocker_clearance_plan": _blocker_clearance_plan(blocked, provider_env=provider_env),
        "deployment_discovery": {
            "artifact": str(deployment_discovery_path),
            "found": bool(deployment_discovery.get("found")),
            "candidate_web_app_origin": web_app_origin_candidate,
            "usable_as_web_app_origin_candidate": bool(
                deployment_discovery.get("usable_as_web_app_origin_candidate")
            ),
            "clears_launch_blockers": bool(deployment_discovery.get("clears_launch_blockers")),
            "launch_blocker_note": deployment_discovery.get("launch_blocker_note"),
            "current_head_deployments": deployment_discovery.get("current_head_deployments") or [],
            "historical_production_candidates": deployment_discovery.get("historical_production_candidates") or [],
        },
        "web_app_deployment_probe": {
            "artifact": str(web_app_probe_path),
            "client_bundle_usable": bool(web_app_probe.get("client_bundle_usable")),
            "web_app_url": web_app_probe.get("web_app_url"),
            "detected_vite_hub_url": web_app_probe.get("detected_vite_hub_url"),
            "detected_preview_pipeline": web_app_probe.get("detected_preview_pipeline"),
            "clears_launch_blockers": bool(web_app_probe.get("clears_launch_blockers")),
            "vercel_protection_bypass_configured": bool(
                web_app_probe.get("vercel_protection_bypass_configured")
            ),
            "vercel_protection_bypass_env": web_app_probe.get("vercel_protection_bypass_env"),
            "failures": web_app_probe.get("failures") or [],
            "warnings": web_app_probe.get("warnings") or [],
        },
        "source_artifacts": {
            "completion_audit": str(ROOT / "reports" / "launch" / "completion_audit.json"),
            "launch_report": str(ROOT / "reports" / "launch" / "latest.json"),
            "preflight": str(ROOT / "reports" / "launch" / "preflight.json"),
            "deployment_discovery": str(deployment_discovery_path),
            "web_app_deployment_probe": str(web_app_probe_path),
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

    discovery = handoff.get("deployment_discovery") or {}
    if discovery.get("found") or discovery.get("candidate_web_app_origin"):
        lines.extend(
            [
                "",
                "## Discovered Deployment Metadata",
                "",
                f"- Candidate WEB_APP_ORIGIN: `{discovery.get('candidate_web_app_origin') or 'none'}`",
                f"- Usable as WEB_APP_ORIGIN candidate: `{discovery.get('usable_as_web_app_origin_candidate')}`",
                f"- Clears launch blockers: `{discovery.get('clears_launch_blockers')}`",
                f"- Operator note: {discovery.get('launch_blocker_note')}",
                "",
                "| Deployment | Environment | SHA | Vercel origin |",
                "|---|---|---|---|",
            ]
        )
        current_deployments = discovery.get("current_head_deployments") or []
        if current_deployments:
            for deployment in current_deployments:
                lines.append(
                    f"| `{_md_cell(deployment.get('id'))}` | "
                    f"`{_md_cell(deployment.get('environment'))}` | "
                    f"`{_md_cell(deployment.get('sha'))}` | "
                    f"`{_md_cell(deployment.get('successful_vercel_origin') or 'none')}` |"
                )
        else:
            lines.append("| `none` | `none` | `none` | `none` |")

    web_probe = handoff.get("web_app_deployment_probe") or {}
    if web_probe.get("failures") or web_probe.get("web_app_url") or web_probe.get("detected_vite_hub_url"):
        lines.extend(
            [
                "",
                "## Web App Deployment Probe",
                "",
                f"- Web app URL: `{web_probe.get('web_app_url') or 'unset'}`",
                f"- Client bundle usable: `{web_probe.get('client_bundle_usable')}`",
                f"- Detected VITE_HUB_URL: `{web_probe.get('detected_vite_hub_url') or 'none'}`",
                f"- Detected VITE_PRESET_PREVIEW_PIPELINE: `{web_probe.get('detected_preview_pipeline') or 'none'}`",
                f"- Clears launch blockers: `{web_probe.get('clears_launch_blockers')}`",
                "",
                "Failures:",
            ]
        )
        failures = web_probe.get("failures") or []
        if failures:
            for failure in failures:
                lines.append(f"- `{failure}`")
        else:
            lines.append("- `none`")

    lines.extend(["", "## Commands", "", "```bash", *handoff["commands"], "```", "", "## Open Blockers", ""])
    for blocker in handoff["open_blockers"]:
        values = ", ".join(f"`{value}`" for value in blocker["blockers"]) or "`none`"
        lines.append(f"- `{blocker['id']}`: {values}")

    lines.extend(["", "## Blocker Clearance Plan", "", "| Blocker | Operator action | Evidence to expect |", "|---|---|---|"])
    for item in handoff["blocker_clearance_plan"]:
        lines.append(f"| `{_md_cell(item['id'])}` | {_md_cell(item['action'])} | {_md_cell(item['evidence'])} |")

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
