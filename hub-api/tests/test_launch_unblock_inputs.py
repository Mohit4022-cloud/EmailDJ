from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_artifacts(root: Path) -> None:
    _write_json(
        root / "reports" / "launch" / "completion_audit.json",
        {
            "final_status": "not_complete",
            "items": [
                {
                    "id": "deployed_preflight_inputs",
                    "requirement": "Operator exports deployed launch inputs.",
                    "status": "blocked",
                    "blockers": ["STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY"],
                },
                {
                    "id": "durable_infra",
                    "requirement": "Use durable datastores.",
                    "status": "blocked",
                    "blockers": ["redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory"],
                },
                {
                    "id": "pinned_origins_beta_provider",
                    "requirement": "Pin deployed origins, beta keys, and provider mode.",
                    "status": "blocked",
                    "blockers": ["web_app_origin_not_pinned:unset"],
                },
            ],
        },
    )
    _write_json(
        root / "reports" / "launch" / "latest.json",
        {
            "final_recommendation": "Not yet launch-ready",
            "effective_provider": "anthropic",
            "launch_mode": "limited_rollout",
        },
    )
    _write_json(
        root / "reports" / "launch" / "preflight.json",
        {
            "ready": False,
            "provider": "anthropic",
            "provider_env": "ANTHROPIC_API_KEY",
            "missing_inputs": [
                "STAGING_BASE_URL",
                "PROD_BASE_URL",
                "BETA_KEY",
                "VERCEL_AUTOMATION_BYPASS_SECRET",
            ],
        },
    )
    _write_json(
        root / "reports" / "launch" / "deployment_discovery.json",
        {
            "found": True,
            "candidate_web_app_origin": "https://emaildj-preview.example.vercel.app",
            "usable_as_web_app_origin_candidate": True,
            "clears_launch_blockers": False,
            "current_head_deployments": [],
            "historical_production_candidates": [],
        },
    )
    _write_json(
        root / "reports" / "launch" / "web_app_deployment_probe.json",
        {
            "web_app_url": "https://emaildj-preview.example.vercel.app",
            "client_bundle_usable": False,
            "clears_launch_blockers": False,
            "failures": [
                "http_error:401",
                "web_app_deployment_requires_auth_or_vercel_protection_bypass",
                "vercel_protection_bypass_secret_missing",
            ],
        },
    )


def test_launch_unblock_inputs_filters_to_required_operator_values(monkeypatch, tmp_path):
    import scripts.launch_handoff as handoff
    import scripts.launch_unblock_inputs as unblock

    root = tmp_path / "repo" / "hub-api"
    _write_artifacts(root)
    monkeypatch.setattr(handoff, "ROOT", root)
    monkeypatch.setattr(handoff, "REPO_ROOT", root.parent)
    monkeypatch.setattr(unblock, "ROOT", root)

    payload = unblock.build_launch_unblock_inputs()
    shell_names = {item["name"] for item in payload["required_shell_exports"]}
    dashboard_inputs = {item["name"]: item for item in payload["required_dashboard_inputs"]}

    assert payload["current_status"] == "not_complete"
    assert payload["provider"] == "anthropic"
    assert payload["provider_env"] == "ANTHROPIC_API_KEY"
    assert {
        "STAGING_BASE_URL",
        "PROD_BASE_URL",
        "BETA_KEY",
        "ANTHROPIC_API_KEY",
        "VERCEL_AUTOMATION_BYPASS_SECRET",
        "VITE_HUB_URL",
        "VITE_EMAILDJ_BETA_KEY",
    } <= shell_names
    assert dashboard_inputs["WEB_APP_ORIGIN"]["candidate_value"] == (
        "https://emaildj-preview.example.vercel.app"
    )
    assert {"REDIS_URL", "DATABASE_URL", "VECTOR_STORE_BACKEND"} <= set(dashboard_inputs)
    assert 'export STAGING_BASE_URL="https://<staging-hub-api-root>"' in payload["shell_export_template"]
    assert "placeholder-only" in payload["operator_contract"]
    assert payload["blocked_evidence_refresh_commands"][0]["id"] == "web_app_deployment_probe_readout"
    assert "make launch-verify-deployed" in payload["next_commands"]


def test_launch_unblock_inputs_writes_json_and_markdown(monkeypatch, tmp_path):
    import scripts.launch_handoff as handoff
    import scripts.launch_unblock_inputs as unblock

    root = tmp_path / "repo" / "hub-api"
    _write_artifacts(root)
    monkeypatch.setattr(handoff, "ROOT", root)
    monkeypatch.setattr(handoff, "REPO_ROOT", root.parent)
    monkeypatch.setattr(unblock, "ROOT", root)

    json_path, md_path, payload = unblock.write_launch_unblock_inputs()

    assert json_path.exists()
    assert md_path.exists()
    assert payload["required_shell_exports"]
    markdown = md_path.read_text(encoding="utf-8")
    assert "Launch Unblock Inputs" in markdown
    assert "Paste-Safe Shell Exports" in markdown
    assert 'export STAGING_BASE_URL="https://<staging-hub-api-root>"' in markdown
    assert "`WEB_APP_ORIGIN`" in markdown
    assert "https://emaildj-preview.example.vercel.app" in markdown
    assert "Blocked Evidence Refresh" in markdown
    assert "Blocker Clearance Plan" in markdown
