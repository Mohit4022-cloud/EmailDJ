from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_artifacts(root: Path, *, provider: str = "openai", provider_env: str = "OPENAI_API_KEY") -> None:
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
                {
                    "id": "hub_api_full_suite",
                    "requirement": "Keep backend green.",
                    "status": "pass",
                    "blockers": [],
                },
            ],
        },
    )
    _write_json(
        root / "reports" / "launch" / "latest.json",
        {
            "final_recommendation": "Not yet launch-ready",
            "effective_provider": provider,
            "launch_mode": "limited_rollout",
        },
    )
    _write_json(
        root / "reports" / "launch" / "preflight.json",
        {
            "ready": False,
            "provider": provider,
            "provider_env": provider_env,
            "required_inputs_present": {
                "STAGING_BASE_URL": False,
                "PROD_BASE_URL": False,
                "BETA_KEY": False,
                provider_env: True,
            },
            "missing_inputs": ["STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY"],
            "operator_input_errors": [],
        },
    )


def _write_deployment_discovery(root: Path) -> None:
    _write_json(
        root / "reports" / "launch" / "deployment_discovery.json",
        {
            "generated_at": "2026-05-07T20:30:00Z",
            "found": True,
            "current_git_sha": "4f323ae5ee8530886f267733f85c3c2061d27ca1",
            "candidate_web_app_origin": "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app",
            "usable_as_web_app_origin_candidate": True,
            "clears_launch_blockers": False,
            "launch_blocker_note": (
                "Deployment metadata only identifies candidate web origins. It does not clear launch blockers until the Hub API "
                "deployment pins WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, beta keys, provider mode, and fresh runtime snapshots."
            ),
            "current_head_deployments": [
                {
                    "id": 4614098730,
                    "environment": "Preview",
                    "sha": "4f323ae5ee8530886f267733f85c3c2061d27ca1",
                    "successful_vercel_origin": "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app",
                }
            ],
            "historical_production_candidates": [],
        },
    )


def test_launch_handoff_translates_blockers_into_operator_inputs(monkeypatch, tmp_path):
    import scripts.launch_handoff as handoff

    root = tmp_path / "repo" / "hub-api"
    repo_root = root.parent
    _write_artifacts(root, provider="anthropic", provider_env="ANTHROPIC_API_KEY")
    monkeypatch.setattr(handoff, "ROOT", root)
    monkeypatch.setattr(handoff, "REPO_ROOT", repo_root)

    payload = handoff.build_launch_handoff()
    export_names = {item["name"] for item in payload["required_exports"] if item["required_when"]}
    dashboard_inputs = {item["name"]: item for item in payload["dashboard_inputs"]}

    assert payload["current_status"] == "not_complete"
    assert payload["provider"] == "anthropic"
    assert payload["provider_env"] == "ANTHROPIC_API_KEY"
    assert {"STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY"} <= export_names
    assert {"VITE_HUB_URL", "VITE_EMAILDJ_BETA_KEY", "VITE_PRESET_PREVIEW_PIPELINE"} <= export_names
    assert dashboard_inputs["EMAILDJ_REAL_PROVIDER"]["value"] == "anthropic"
    assert dashboard_inputs["ANTHROPIC_API_KEY"]["required_when"] is True
    assert dashboard_inputs["REDIS_URL"]["required_when"] is True
    clearance = {item["id"]: item for item in payload["blocker_clearance_plan"]}
    assert "deployed_preflight_inputs" in clearance
    assert "durable_infra" in clearance
    assert "ANTHROPIC_API_KEY" in clearance["pinned_origins_beta_provider"]["action"]
    assert payload["commands"] == [
        "make render-blueprint-check",
        "make launch-preflight",
        "make launch-verify-deployed",
        "make launch-audit",
        "make launch-discover-deployment",
        "make launch-handoff",
    ]


def test_launch_handoff_writes_json_and_markdown(monkeypatch, tmp_path):
    import scripts.launch_handoff as handoff

    root = tmp_path / "repo" / "hub-api"
    repo_root = root.parent
    _write_artifacts(root)
    monkeypatch.setattr(handoff, "ROOT", root)
    monkeypatch.setattr(handoff, "REPO_ROOT", repo_root)

    json_path, md_path, payload = handoff.write_launch_handoff()

    assert json_path.exists()
    assert md_path.exists()
    assert payload["provider_env"] == "OPENAI_API_KEY"
    markdown = md_path.read_text(encoding="utf-8")
    assert "Launch Operator Handoff" in markdown
    assert 'export STAGING_BASE_URL="https://<staging-hub-api-root>"' in markdown
    assert 'export VITE_EMAILDJ_BETA_KEY="$BETA_KEY"' in markdown
    assert "`OPENAI_API_KEY`" in markdown
    assert "Blocker Clearance Plan" in markdown
    assert "hub-api/reports/launch/preflight.json has ready=true" in markdown


def test_launch_handoff_includes_deployment_discovery_without_clearing_blockers(monkeypatch, tmp_path):
    import scripts.launch_handoff as handoff

    root = tmp_path / "repo" / "hub-api"
    repo_root = root.parent
    _write_artifacts(root)
    _write_deployment_discovery(root)
    monkeypatch.setattr(handoff, "ROOT", root)
    monkeypatch.setattr(handoff, "REPO_ROOT", repo_root)

    json_path, md_path, payload = handoff.write_launch_handoff()
    dashboard_inputs = {item["name"]: item for item in payload["dashboard_inputs"]}

    assert json_path.exists()
    assert payload["deployment_discovery"]["candidate_web_app_origin"] == (
        "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app"
    )
    assert payload["deployment_discovery"]["clears_launch_blockers"] is False
    assert dashboard_inputs["WEB_APP_ORIGIN"]["value"] == "https://<deployed-web-app-origin>"
    assert dashboard_inputs["WEB_APP_ORIGIN"]["candidate_value"] == (
        "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app"
    )

    markdown = md_path.read_text(encoding="utf-8")
    assert "Discovered Deployment Metadata" in markdown
    assert "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app" in markdown
    assert "Clears launch blockers: `False`" in markdown
