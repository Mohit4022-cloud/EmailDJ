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
    assert payload["commands"] == [
        "make render-blueprint-check",
        "make launch-preflight",
        "make launch-verify-deployed",
        "make launch-audit",
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
