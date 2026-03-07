from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _now_text() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_launch_check_limited_rollout_allows_provider_not_run(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "limited_rollout")

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

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["backend_green"] == "green"
    assert report["harness_green"] == "green"
    assert report["shim_green"] == "green"
    assert report["provider_green"] == "not_run"
    assert report["remix_green"] == "green"
    assert report["provider_source"] == "provider_shim"
    assert report["final_recommendation"] == "Stable for MVP launch behind limited rollout"


def test_launch_check_prefers_external_provider_artifacts(monkeypatch, tmp_path):
    import scripts.launch_check as lc

    monkeypatch.setattr(lc, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "broad_launch")

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

    report = lc._read_launch_report(localhost_smoke_summary="", max_age_hours=72)

    assert report["provider_green"] == "green"
    assert report["provider_source"] == "external_provider"
    assert report["claims_policy_intervention_count"] == 3
    assert report["final_recommendation"] == "Not yet launch-ready"


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
