from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_base_artifacts(root: Path, repo_root: Path, *, ready: bool = False) -> None:
    blockers = [] if ready else [
        "chrome_extension_origin_not_pinned:default_dev_placeholder",
        "database_not_durable_for_launch_mode:limited_rollout:default_local_sqlite",
        "http_smoke_external_provider_missing_for_launch_mode:limited_rollout",
        "redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory",
        "vector_store_not_durable_for_launch_mode:limited_rollout:memory_backend",
        "web_app_origin_not_pinned:unset",
    ]
    warnings = [] if ready else [
        "production_runtime_snapshot_missing",
        "release_fingerprint_unavailable",
        "staging_runtime_snapshot_missing",
    ]
    _write_json(
        root / "reports" / "launch" / "latest.json",
        {
            "generated_at": "2026-05-07T16:11:36Z",
            "final_recommendation": "Stable for MVP launch behind limited rollout" if ready else "Not yet launch-ready",
            "backend_green": "green",
            "render_blueprint_green": "green",
            "harness_green": "green",
            "provider_green": "green",
            "provider_source": "external_provider",
            "provider_stub_enabled": False,
            "effective_provider_source": "external_provider",
            "validation_fallback_allowed": False,
            "validation_fallback_policy": "dev_only_fail_closed_in_launch_modes",
            "release_fingerprint_available": ready,
            "release_fingerprint": "git_sha=abc123" if ready else None,
            "web_app_origin_state": "explicit_pinned" if ready else "unset",
            "chrome_extension_origin": "chrome-extension://emaildj-prod" if ready else "chrome-extension://dev",
            "chrome_extension_origin_state": "explicit_pinned" if ready else "default_dev_placeholder",
            "beta_keys_state": "explicit_pinned",
            "redis_config_state": "external_redis_configured" if ready else "forced_inmemory",
            "database_config_state": "external_postgres_configured" if ready else "default_local_sqlite",
            "vector_store_config_state": "pgvector_configured" if ready else "memory_backend",
            "required_http_smoke_routes": ["generate", "remix"],
            "localhost_smoke": {"provider_source_counts": {"external_provider": 30} if ready else {"provider_stub": 30}},
            "artifact_provenance": {
                "staging_runtime_snapshot": {"missing": not ready},
                "production_runtime_snapshot": {"missing": not ready},
            },
            "release_fingerprint_parity": {"runtime_source_used": "production_runtime_snapshot" if ready else "local_env"},
            "config_blockers": blockers,
            "config_warnings": warnings,
        },
    )
    _write_json(
        root / "reports" / "launch" / "preflight.json",
        {
            "ready": ready,
            "failure_bucket": None if ready else "operator_input_missing",
            "required_inputs_present": {
                "STAGING_BASE_URL": ready,
                "PROD_BASE_URL": ready,
                "BETA_KEY": ready,
                "OPENAI_API_KEY": True,
            },
            "missing_inputs": [] if ready else ["STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY"],
            "operator_input_errors": [],
        },
    )
    _write_json(
        root / "reports" / "launch" / "web_app_deployment_probe.json",
        {
            "client_bundle_usable": ready,
            "detected_vite_hub_url": "https://hub.example.com" if ready else None,
            "detected_preview_pipeline": "off" if ready else None,
            "failures": [] if ready else ["http_error:401"],
            "clears_launch_blockers": False,
        },
    )
    _write_json(
        root / "reports" / "launch" / "backend_suite.json",
        {"ok": True, "backend_green": "green", "summary": "389 passed"},
    )
    _write_json(
        root / "reports" / "provider_stub" / "latest.json",
        {"summary": {"passed_cases": 96, "total_cases": 96, "failed_cases": 0, "pass_rate": 1.0}},
    )
    _write_json(
        root / "reports" / "external_provider" / "latest.json",
        {
            "summary": {
                "provider_source": "external_provider",
                "passed_cases": 10,
                "total_cases": 10,
                "failed_cases": 0,
            }
        },
    )
    _write_json(
        repo_root / "docs" / "ops" / "launch_surfaces.json",
        {
            "launch_owned": [{"path": "hub-api/"}, {"path": "web-app/"}, {"path": "chrome-extension/"}],
            "legacy_explicit_only": [
                {"path": "backend/", "launch_readiness_evidence": False},
                {"path": "frontend/", "launch_readiness_evidence": False},
            ],
        },
    )
    (repo_root / "web-app" / "tests").mkdir(parents=True, exist_ok=True)
    (repo_root / "web-app" / "src" / "components").mkdir(parents=True, exist_ok=True)
    (repo_root / "web-app" / "tests" / "layout-contract.test.js").write_text(
        "draft editor owns the primary canvas chrome and empty state\n"
        "mobile workspace controls stay within the viewport grid\n",
        encoding="utf-8",
    )
    (repo_root / "web-app" / "src" / "components" / "EmailEditor.js").write_text(
        'id="editorFrame"\nid="draftCanvasTitle"\n',
        encoding="utf-8",
    )


def test_launch_audit_marks_external_blockers(monkeypatch, tmp_path):
    import scripts.launch_audit as audit

    repo_root = tmp_path / "repo"
    root = repo_root / "hub-api"
    _write_base_artifacts(root, repo_root, ready=False)
    monkeypatch.setattr(audit, "ROOT", root)
    monkeypatch.setattr(audit, "REPO_ROOT", repo_root)

    payload = audit.build_launch_audit()
    blocked_ids = {item["id"] for item in payload["items"] if item["status"] == "blocked"}

    assert payload["final_status"] == "not_complete"
    assert "deployed_preflight_inputs" in blocked_ids
    assert "runtime_snapshots" in blocked_ids
    assert "durable_infra" in blocked_ids
    assert "deployed_http_smoke" in blocked_ids
    deployed_http = {item["id"]: item for item in payload["items"]}["deployed_http_smoke"]
    assert "web_app_deployment_probe_not_usable" in deployed_http["blockers"]
    assert "web_app_deployment_probe:http_error:401" in deployed_http["blockers"]
    assert "parallel_stack_story" not in blocked_ids
    assert "draft_workspace_ux" not in blocked_ids
    checklist = {item["number"]: item for item in payload["objective_checklist"]}
    assert len(checklist) == 10
    assert checklist[1]["status"] == "pass"
    assert checklist[4]["status"] == "blocked"
    assert checklist[5]["mapped_requirements"] == [
        "pinned_origins_beta_provider",
        "validation_fallback_fail_closed",
        "release_fingerprint_parity",
    ]
    assert checklist[6]["mapped_requirements"] == ["deployed_http_smoke"]
    assert "Limited rollout proves generate/remix" in checklist[6]["note"]


def test_launch_audit_can_mark_complete_when_artifacts_cover_requirements(monkeypatch, tmp_path):
    import scripts.launch_audit as audit

    repo_root = tmp_path / "repo"
    root = repo_root / "hub-api"
    _write_base_artifacts(root, repo_root, ready=True)
    monkeypatch.setattr(audit, "ROOT", root)
    monkeypatch.setattr(audit, "REPO_ROOT", repo_root)

    payload = audit.build_launch_audit()

    assert payload["final_status"] == "complete"
    assert payload["open_blocker_count"] == 0
    assert all(item["status"] == "pass" for item in payload["objective_checklist"])


def test_launch_audit_blocks_validation_fallback_policy(monkeypatch, tmp_path):
    import scripts.launch_audit as audit

    repo_root = tmp_path / "repo"
    root = repo_root / "hub-api"
    _write_base_artifacts(root, repo_root, ready=True)
    latest_path = root / "reports" / "launch" / "latest.json"
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["validation_fallback_allowed"] = True
    latest["config_blockers"] = ["validation_fallback_enabled_for_launch_mode:limited_rollout"]
    latest["final_recommendation"] = "Not yet launch-ready"
    latest_path.write_text(json.dumps(latest, indent=2), encoding="utf-8")
    monkeypatch.setattr(audit, "ROOT", root)
    monkeypatch.setattr(audit, "REPO_ROOT", repo_root)

    payload = audit.build_launch_audit()
    item = next(item for item in payload["items"] if item["id"] == "validation_fallback_fail_closed")
    checklist = {item["number"]: item for item in payload["objective_checklist"]}

    assert item["status"] == "blocked"
    assert "validation_fallback_enabled_for_launch_mode:limited_rollout" in item["blockers"]
    assert checklist[5]["status"] == "blocked"


def test_launch_audit_writes_json_and_markdown(monkeypatch, tmp_path):
    import scripts.launch_audit as audit

    repo_root = tmp_path / "repo"
    root = repo_root / "hub-api"
    _write_base_artifacts(root, repo_root, ready=False)
    monkeypatch.setattr(audit, "ROOT", root)
    monkeypatch.setattr(audit, "REPO_ROOT", repo_root)

    json_path, md_path, payload = audit.write_launch_audit()

    assert json_path.exists()
    assert md_path.exists()
    assert payload["final_status"] == "not_complete"
    markdown = md_path.read_text(encoding="utf-8")
    assert "Launch Completion Audit" in markdown
    assert "A-Z Objective Checklist" in markdown
