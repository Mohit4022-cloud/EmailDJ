from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _now_text(hours_ago: int = 0) -> str:
    value = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return value.isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _runtime_snapshot_payload(**overrides) -> dict:
    payload = {
        "generated_at_utc": _now_text(),
        "app_env": "staging",
        "runtime_mode": "real",
        "quick_generate_mode": "real",
        "configured_quick_generate_mode": None,
        "effective_quick_generate_mode": "real",
        "provider_stub_enabled": False,
        "real_provider_preference": "openai",
        "effective_provider_source": "external_provider",
        "effective_provider": "openai",
        "effective_model": "gpt-5-nano",
        "effective_model_identifier": "openai/gpt-5-nano",
        "launch_mode": "limited_rollout",
        "route_gates": {"generate": True, "remix": True, "preview": False},
        "route_gate_sources": {
            "generate": "launch_mode:limited_rollout",
            "remix": "launch_mode:limited_rollout",
            "preview": "launch_mode:limited_rollout",
        },
        "preview_pipeline_enabled": False,
        "release_fingerprint_available": True,
        "git_sha": "abc123def456",
        "build_id": None,
        "image_tag": None,
        "release_version": None,
        "release_fingerprint": "git_sha=abc123def456",
        "chrome_extension_origin": "chrome-extension://emaildj-prod",
        "chrome_extension_origin_state": "explicit_pinned",
        "web_app_origin": "https://app.emaildj.test",
        "web_app_origin_state": "explicit_pinned",
        "beta_keys_state": "explicit_pinned",
        "web_rate_limit_per_min": 300,
        "web_rate_limit_source": "explicit_env",
    }
    payload.update(overrides)
    return payload


def _write_runtime_snapshots(root: Path, *, staging: dict | None = None, production: dict | None = None) -> None:
    if staging is not None:
        _write_json(root / "reports" / "launch" / "runtime_snapshots" / "staging.json", staging)
    if production is not None:
        _write_json(root / "reports" / "launch" / "runtime_snapshots" / "production.json", production)


def _write_launch_artifacts(root: Path, *, backend_hours_ago: int = 0) -> None:
    _write_json(
        root / "reports" / "launch" / "backend_suite.json",
        {"generated_at": _now_text(backend_hours_ago), "backend_green": "green", "ok": True},
    )
    _write_json(
        root / "reports" / "provider_stub" / "latest.json",
        {
            "generated_at": _now_text(),
            "summary": {
                "failed_cases": 0,
                "provider_source": "provider_stub",
                "required_field_miss_count": 0,
                "under_length_miss_count": 0,
                "top_violation_codes": {},
                "claims_policy_intervention_count": 0,
            },
        },
    )
    _write_json(
        root / "reports" / "external_provider" / "latest.json",
        {
            "generated_at": _now_text(),
            "summary": {
                "failed_cases": 0,
                "provider_source": "external_provider",
                "required_field_miss_count": 0,
                "under_length_miss_count": 0,
                "top_violation_codes": {},
                "claims_policy_intervention_count": 0,
            },
        },
    )
    _write_json(
        root / "debug_runs" / "ui_sessions_codex" / "20260307T211701Z" / "summary.json",
        {
            "captured_at_utc": _now_text(),
            "provider_source": "provider_shim",
            "launch_gates": {
                "shim_green": "green",
                "provider_green": "not_run",
                "remix_green": "green",
            },
        },
    )
    _write_json(
        root / "debug_runs" / "ui_sessions" / "20260307T211602Z" / "summary.json",
        {
            "captured_at_utc": _now_text(),
            "provider_source": "external_provider",
            "launch_gates": {
                "shim_green": "not_run",
                "provider_green": "green",
                "remix_green": "green",
            },
        },
    )


def test_launch_check_limited_rollout_allows_provider_not_run(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "limited_rollout")
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("USE_PROVIDER_STUB", "0")
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("WEB_APP_ORIGIN", "https://staging.emaildj.test")
    monkeypatch.setenv("EMAILDJ_WEB_BETA_KEYS", "ops-beta-key")
    monkeypatch.setenv("CHROME_EXTENSION_ORIGIN", "chrome-extension://emaildj-staging")
    monkeypatch.setenv("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")

    _write_json(
        tmp_path / "reports" / "launch" / "backend_suite.json",
        {"generated_at": _now_text(), "backend_green": "green", "ok": True},
    )
    _write_json(
        tmp_path / "reports" / "provider_stub" / "latest.json",
        {
            "generated_at": _now_text(),
            "summary": {
                "failed_cases": 0,
                "provider_source": "provider_stub",
                "required_field_miss_count": 0,
                "under_length_miss_count": 0,
                "top_violation_codes": {},
                "claims_policy_intervention_count": 0,
            },
        },
    )
    _write_json(
        tmp_path / "debug_runs" / "ui_sessions_codex" / "20260307T211701Z" / "summary.json",
        {
            "captured_at_utc": _now_text(),
            "provider_source": "provider_shim",
            "launch_gates": {
                "shim_green": "green",
                "provider_green": "not_run",
                "remix_green": "green",
            },
        },
    )
    staging = _runtime_snapshot_payload()
    production = _runtime_snapshot_payload()
    _write_runtime_snapshots(tmp_path, staging=staging, production=production)

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["backend_green"] == "green"
    assert report["harness_green"] == "green"
    assert report["shim_green"] == "green"
    assert report["provider_green"] == "not_run"
    assert report["remix_green"] == "green"
    assert report["provider_source"] == "provider_shim"
    assert report["runtime_mode"] == "real"
    assert report["provider_stub_enabled"] is False
    assert report["real_provider_preference"] == "openai"
    assert report["effective_provider_source"] == "external_provider"
    assert report["route_gates"] == {"generate": True, "remix": True, "preview": False}
    assert report["route_gate_sources"]["preview"] == "launch_mode:limited_rollout"
    assert report["config_blockers"] == []
    assert report["config_warnings"] == []
    assert report["final_recommendation"] == "Stable for MVP launch behind limited rollout"


def test_launch_check_prefers_external_provider_artifacts(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "broad_launch")
    monkeypatch.setenv("CHROME_EXTENSION_ORIGIN", "chrome-extension://emaildj-staging")
    monkeypatch.setenv("WEB_APP_ORIGIN", "https://staging.emaildj.test")
    monkeypatch.setenv("EMAILDJ_WEB_BETA_KEYS", "ops-beta-key")
    monkeypatch.setenv("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")

    _write_json(
        tmp_path / "reports" / "launch" / "backend_suite.json",
        {"generated_at": _now_text(), "backend_green": "green", "ok": True},
    )
    _write_json(
        tmp_path / "reports" / "provider_stub" / "latest.json",
        {
            "generated_at": _now_text(),
            "summary": {
                "failed_cases": 0,
                "provider_source": "provider_stub",
                "required_field_miss_count": 0,
                "under_length_miss_count": 0,
                "top_violation_codes": {"CTA_NOT_FINAL": 1},
                "claims_policy_intervention_count": 1,
            },
        },
    )
    _write_json(
        tmp_path / "reports" / "external_provider" / "latest.json",
        {
            "generated_at": _now_text(),
            "summary": {
                "failed_cases": 0,
                "provider_source": "external_provider",
                "required_field_miss_count": 0,
                "under_length_miss_count": 0,
                "top_violation_codes": {"CTA_NOT_FINAL": 1},
                "claims_policy_intervention_count": 3,
            },
        },
    )
    _write_json(
        tmp_path / "debug_runs" / "ui_sessions" / "20260307T211602Z" / "summary.json",
        {
            "captured_at_utc": _now_text(),
            "provider_source": "external_provider",
            "launch_gates": {
                "shim_green": "not_run",
                "provider_green": "green",
                "remix_green": "green",
            },
        },
    )
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(launch_mode="broad_launch"),
        production=_runtime_snapshot_payload(launch_mode="broad_launch"),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["provider_green"] == "green"
    assert report["provider_source"] == "external_provider"
    assert report["claims_policy_intervention_count"] == 3
    assert report["final_recommendation"] == "Not yet launch-ready"


def test_launch_check_uses_dotenv_app_env_when_shell_env_missing(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("EMAILDJ_LAUNCH_MODE", raising=False)
    monkeypatch.setenv("CHROME_EXTENSION_ORIGIN", "chrome-extension://emaildj-staging")
    monkeypatch.setenv("WEB_APP_ORIGIN", "https://staging.emaildj.test")
    monkeypatch.setenv("EMAILDJ_WEB_BETA_KEYS", "ops-beta-key")
    monkeypatch.setenv("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")
    (tmp_path / ".env").write_text("APP_ENV=staging\n", encoding="utf-8")
    _write_launch_artifacts(tmp_path)

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["launch_mode"] == "limited_rollout"
    assert "production_runtime_snapshot_missing" in report["config_warnings"]
    assert report["final_recommendation"] == "Stable for MVP launch behind limited rollout"


def test_launch_check_shell_launch_mode_overrides_dotenv(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "dev")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("CHROME_EXTENSION_ORIGIN", "chrome-extension://emaildj-staging")
    monkeypatch.setenv("WEB_APP_ORIGIN", "https://staging.emaildj.test")
    monkeypatch.setenv("EMAILDJ_WEB_BETA_KEYS", "ops-beta-key")
    monkeypatch.setenv("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")
    (tmp_path / ".env").write_text("APP_ENV=staging\n", encoding="utf-8")
    _write_launch_artifacts(tmp_path)

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["launch_mode"] == "dev"
    assert report["final_recommendation"] == "Stable for broader MVP work"


def test_launch_check_blocks_stub_enabled_limited_rollout(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "limited_rollout")
    monkeypatch.setenv("USE_PROVIDER_STUB", "1")
    monkeypatch.setenv("WEB_APP_ORIGIN", "https://staging.emaildj.test")
    monkeypatch.setenv("EMAILDJ_WEB_BETA_KEYS", "ops-beta-key")
    monkeypatch.setenv("CHROME_EXTENSION_ORIGIN", "chrome-extension://emaildj-staging")
    monkeypatch.setenv("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")
    _write_launch_artifacts(tmp_path)

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["runtime_mode"] == "mock"
    assert report["provider_stub_enabled"] is True
    assert "provider_stub_enabled_for_launch_mode:limited_rollout" in report["config_blockers"]
    assert "resolved_provider_source_not_external_provider:provider_stub" in report["config_blockers"]
    assert report["final_recommendation"] == "Not yet launch-ready"


def test_launch_check_blocks_quick_generate_mode_mismatch(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "limited_rollout")
    monkeypatch.setenv("USE_PROVIDER_STUB", "0")
    monkeypatch.setenv("EMAILDJ_QUICK_GENERATE_MODE", "mock")
    monkeypatch.setenv("WEB_APP_ORIGIN", "https://staging.emaildj.test")
    monkeypatch.setenv("EMAILDJ_WEB_BETA_KEYS", "ops-beta-key")
    monkeypatch.setenv("CHROME_EXTENSION_ORIGIN", "chrome-extension://emaildj-staging")
    monkeypatch.setenv("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", "300")
    _write_launch_artifacts(tmp_path)

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["runtime_mode"] == "real"
    assert report["configured_quick_generate_mode"] == "mock"
    assert "configured_quick_generate_mode_mismatch:mock->real" in report["config_blockers"]
    assert report["final_recommendation"] == "Not yet launch-ready"


def test_launch_check_blocks_release_fingerprint_mismatch(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(git_sha="staging123", release_fingerprint="git_sha=staging123"),
        production=_runtime_snapshot_payload(git_sha="prod456", release_fingerprint="git_sha=prod456"),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert "release_fingerprint_mismatch:git_sha:staging123->prod456" in report["config_blockers"]
    assert report["final_recommendation"] == "Not yet launch-ready"


def test_launch_check_warns_when_release_fingerprint_unavailable(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(
            git_sha=None,
            release_fingerprint=None,
            release_fingerprint_available=False,
        ),
        production=_runtime_snapshot_payload(
            git_sha=None,
            release_fingerprint=None,
            release_fingerprint_available=False,
        ),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert "release_fingerprint_unavailable" in report["config_warnings"]
    assert report["config_blockers"] == []


def test_launch_check_blocks_preview_enabled_limited_rollout(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(
            route_gates={"generate": True, "remix": True, "preview": True},
            route_gate_sources={"generate": "launch_mode:limited_rollout", "remix": "launch_mode:limited_rollout", "preview": "explicit_env"},
        ),
        production=_runtime_snapshot_payload(
            route_gates={"generate": True, "remix": True, "preview": True},
            route_gate_sources={"generate": "launch_mode:limited_rollout", "remix": "launch_mode:limited_rollout", "preview": "explicit_env"},
        ),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert "preview_route_enabled_for_launch_mode:limited_rollout" in report["config_blockers"]


def test_launch_check_blocks_missing_or_default_origins(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(
            chrome_extension_origin=None,
            chrome_extension_origin_state="unset",
            web_app_origin="http://localhost:5174",
            web_app_origin_state="default_dev_placeholder",
        ),
        production=_runtime_snapshot_payload(
            chrome_extension_origin="chrome-extension://dev",
            chrome_extension_origin_state="default_dev_placeholder",
            web_app_origin=None,
            web_app_origin_state="unset",
        ),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert "chrome_extension_origin_not_pinned:default_dev_placeholder" in report["config_blockers"]
    assert "web_app_origin_not_pinned:unset" in report["config_blockers"]


def test_launch_check_blocks_default_beta_key(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(beta_keys_state="default_dev_placeholder"),
        production=_runtime_snapshot_payload(beta_keys_state="default_dev_placeholder"),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert "beta_keys_not_safe:default_dev_placeholder" in report["config_blockers"]


def test_launch_check_warns_on_recommended_stale_artifact(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path, backend_hours_ago=50)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(),
        production=_runtime_snapshot_payload(),
    )

    report = lc._read_launch_report(
        localhost_smoke_summary="",
        max_age_hours=72,
        recommended_max_age_hours=48,
    )

    assert "artifact_age_exceeds_recommended_window:backend" in report["config_warnings"]
    assert report["final_recommendation"] == "Stable for MVP launch behind limited rollout"


def test_launch_check_blocks_on_hard_stale_artifact(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path, backend_hours_ago=80)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(),
        production=_runtime_snapshot_payload(),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert any(error.startswith("backend:stale:") for error in report["errors"])
    assert report["final_recommendation"] == "Not yet launch-ready"


def test_launch_check_blocks_resolved_provider_source_mismatch(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(effective_provider_source="provider_stub", effective_provider="provider_stub", effective_model="mock", effective_model_identifier="provider_stub/mock"),
        production=_runtime_snapshot_payload(effective_provider_source="provider_stub", effective_provider="provider_stub", effective_model="mock", effective_model_identifier="provider_stub/mock"),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert "resolved_provider_source_not_external_provider:provider_stub" in report["config_blockers"]


def test_launch_check_markdown_includes_runtime_config_sections(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    _write_launch_artifacts(tmp_path)
    _write_runtime_snapshots(
        tmp_path,
        staging=_runtime_snapshot_payload(),
        production=_runtime_snapshot_payload(),
    )

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)
    _, md_path = lc._write_launch_report(report)
    markdown = md_path.read_text(encoding="utf-8")

    assert "## Release Fingerprint Parity" in markdown
    assert "## Resolved Runtime Path" in markdown
    assert "## Preview Route Invariant" in markdown
    assert "## Artifact Freshness And Provenance" in markdown
    assert "## Origin And Beta-Key Safety" in markdown
    assert "`effective_provider_source`" in markdown
    assert "`effective_provider_model_identifier`" in markdown
    assert "`comparison_fields`" in markdown


def test_launch_check_uses_provider_specific_report_dirs():
    from evals.runner import _resolved_report_dir

    assert _resolved_report_dir("reports", mode="mock") == Path("reports/provider_stub")
    assert _resolved_report_dir("reports", mode="real") == Path("reports/external_provider")
    assert _resolved_report_dir("/tmp/reports", mode="mock") == Path("/tmp/reports/provider_stub")
    assert _resolved_report_dir("reports/custom", mode="real") == Path("reports/custom")


def test_capture_ui_session_reports_required_external_provider_env(monkeypatch):
    from scripts.capture_ui_session import _required_external_provider_env

    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "anthropic")
    assert _required_external_provider_env() == ("anthropic", "ANTHROPIC_API_KEY")


def test_capture_ui_session_treats_repaired_remix_as_clean():
    from scripts.capture_ui_session import _remix_record_clean

    repaired = {
        "trace_status": "ok",
        "stream_done": {
            "generation_status": "ok",
            "repaired": True,
            "violation_codes": ["invalid_json_output"],
            "fallback_reason": None,
            "final": {
                "subject": "SignalForge's operational support Studio",
                "body": "Hi Alex, final repaired body.\n\nOpen to a quick chat to see if this is relevant?",
            },
        },
    }

    assert _remix_record_clean(repaired) is True


def test_capture_ui_session_keeps_warn_parse_fallback_red():
    from scripts.capture_ui_session import _remix_record_clean

    failed = {
        "trace_status": "warn_parse_fallback",
        "stream_done": {
            "generation_status": "ok",
            "violation_codes": ["invalid_json_output"],
            "fallback_reason": None,
            "final": {
                "subject": "",
                "body": "",
            },
        },
    }

    assert _remix_record_clean(failed) is False
