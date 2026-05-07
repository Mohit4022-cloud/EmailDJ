from __future__ import annotations

import json
from pathlib import Path
import sys

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_deployment_discovery(root: Path) -> None:
    _write_json(
        root / "reports" / "launch" / "deployment_discovery.json",
        {
            "generated_at": "2026-05-07T20:58:58Z",
            "found": True,
            "candidate_web_app_origin": "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app",
            "usable_as_web_app_origin_candidate": True,
            "clears_launch_blockers": False,
            "launch_blocker_note": "candidate only",
        },
    )


def _write_vercel_auth_probe(root: Path) -> None:
    _write_json(
        root / "reports" / "launch" / "web_app_deployment_probe.json",
        {
            "client_bundle_usable": False,
            "source_git_sha": "current-sha",
            "workspace_git_sha_at_probe": "current-sha",
            "failures": [
                "http_error:401",
                "web_app_deployment_requires_auth",
                "web_app_deployment_requires_auth_or_vercel_protection_bypass",
                "vercel_protection_bypass_secret_missing",
            ],
        },
    )


def test_launch_preflight_blocks_missing_inputs_without_transport_probe(monkeypatch):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", Path("/tmp/emaildj-missing-preflight-env"))
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("STAGING_BASE_URL", raising=False)
    monkeypatch.delenv("PROD_BASE_URL", raising=False)
    monkeypatch.delenv("BETA_KEY", raising=False)

    def fail_get(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("transport probe should not run when required inputs are missing")

    monkeypatch.setattr(lp.httpx, "get", fail_get)

    result = lp.run_launch_preflight()

    assert result["ready"] is False
    assert result["failure_bucket"] == "operator_input_missing"
    assert result["transport_checked"] is False
    assert result["missing_inputs"] == ["STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY"]
    assert result["operator_input_sources"]["BETA_KEY"] == {
        "explicit_env_present": False,
        "dotenv_value_present": False,
        "dotenv_value_ignored": False,
        "effective_present": False,
    }
    assert "hub-api root URL" in result["next_steps"][0]
    assert "hub-api root URL" in result["next_steps"][1]
    assert "EMAILDJ_WEB_BETA_KEYS" in result["next_steps"][2]


def test_launch_preflight_marks_discovered_web_origin_as_frontend_only(monkeypatch, tmp_path):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", tmp_path)
    _write_deployment_discovery(tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("STAGING_BASE_URL", raising=False)
    monkeypatch.delenv("PROD_BASE_URL", raising=False)
    monkeypatch.delenv("BETA_KEY", raising=False)

    result = lp.run_launch_preflight()
    next_steps = "\n".join(result["next_steps"])

    assert result["ready"] is False
    assert result["deployment_discovery"]["candidate_web_app_origin"] == (
        "https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app"
    )
    assert result["deployment_discovery"]["clears_launch_blockers"] is False
    assert "only for `WEB_APP_ORIGIN`" in next_steps
    assert "do not use it for `STAGING_BASE_URL` or `PROD_BASE_URL`" in next_steps


def test_launch_preflight_requires_vercel_bypass_when_web_probe_is_auth_gated(monkeypatch, tmp_path):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", tmp_path)
    _write_deployment_discovery(tmp_path)
    _write_vercel_auth_probe(tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PROD_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("BETA_KEY", "ops-beta-key")
    monkeypatch.delenv("VERCEL_AUTOMATION_BYPASS_SECRET", raising=False)

    def fail_get(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("transport probe should not run when Vercel bypass input is missing")

    monkeypatch.setattr(lp.httpx, "get", fail_get)

    result = lp.run_launch_preflight()
    next_steps = "\n".join(result["next_steps"])

    assert result["ready"] is False
    assert result["failure_bucket"] == "operator_input_missing"
    assert result["missing_inputs"] == ["VERCEL_AUTOMATION_BYPASS_SECRET"]
    assert result["required_inputs_present"]["VERCEL_AUTOMATION_BYPASS_SECRET"] is False
    assert result["web_app_probe"]["requires_vercel_protection_bypass"] is True
    assert result["web_app_probe"]["vercel_bypass_env_present"] is False
    assert "x-vercel-protection-bypass" in next_steps


def test_launch_preflight_allows_vercel_bypass_env_when_web_probe_is_auth_gated(monkeypatch, tmp_path):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", tmp_path)
    _write_vercel_auth_probe(tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PROD_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("BETA_KEY", "ops-beta-key")
    monkeypatch.setenv("VERCEL_AUTOMATION_BYPASS_SECRET", "secret")
    monkeypatch.setattr(lp.httpx, "get", lambda *args, **kwargs: _FakeResponse(status_code=200))

    result = lp.run_launch_preflight()

    assert result["ready"] is True
    assert result["required_inputs_present"]["VERCEL_AUTOMATION_BYPASS_SECRET"] is True
    assert result["web_app_probe"]["vercel_bypass_env_present"] is True


def test_launch_preflight_reports_dotenv_operator_inputs_as_ignored(monkeypatch, tmp_path):
    import scripts.launch_preflight as lp

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "STAGING_BASE_URL=https://staging.example.com",
                "PROD_BASE_URL=https://prod.example.com",
                "BETA_KEY=dotenv-beta-key",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(lp, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("STAGING_BASE_URL", raising=False)
    monkeypatch.delenv("PROD_BASE_URL", raising=False)
    monkeypatch.delenv("BETA_KEY", raising=False)

    result = lp.run_launch_preflight()

    assert result["ready"] is False
    assert result["failure_bucket"] == "operator_input_missing"
    assert result["missing_inputs"] == ["STAGING_BASE_URL", "PROD_BASE_URL", "BETA_KEY"]
    assert result["operator_input_sources"]["STAGING_BASE_URL"] == {
        "explicit_env_present": False,
        "dotenv_value_present": True,
        "dotenv_value_ignored": True,
        "effective_present": False,
    }
    assert result["operator_input_sources"]["PROD_BASE_URL"]["dotenv_value_ignored"] is True
    assert result["operator_input_sources"]["BETA_KEY"]["dotenv_value_ignored"] is True


def test_launch_preflight_blocks_transport_failure(monkeypatch, tmp_path):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PROD_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("BETA_KEY", "ops-beta-key")
    monkeypatch.setattr(lp.httpx, "get", lambda *args, **kwargs: (_ for _ in ()).throw(httpx.ConnectError("dns failed")))

    result = lp.run_launch_preflight()

    assert result["ready"] is False
    assert result["failure_bucket"] == "transport_or_provider"
    assert result["transport_checked"] is True
    assert result["transport_ok"] is False
    assert result["transport_error_type"] == "ConnectError"


def test_launch_preflight_blocks_invalid_operator_urls_without_transport_probe(monkeypatch):
    import scripts.launch_preflight as lp

    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "http://localhost:8000/web/v1/debug/config")
    monkeypatch.setenv("PROD_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("BETA_KEY", "dev-beta-key")

    def fail_get(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("transport probe should not run when operator inputs are invalid")

    monkeypatch.setattr(lp.httpx, "get", fail_get)

    result = lp.run_launch_preflight()

    assert result["ready"] is False
    assert result["failure_bucket"] == "operator_input_invalid"
    assert result["transport_checked"] is False
    assert "STAGING_BASE_URL:must_use_https" in result["operator_input_errors"]
    assert "STAGING_BASE_URL:must_not_be_localhost" in result["operator_input_errors"]
    assert "STAGING_BASE_URL:must_be_hub_api_root_url" in result["operator_input_errors"]
    assert "BETA_KEY:must_not_be_dev_placeholder" in result["operator_input_errors"]
    assert "deployed staging hub-api root URL" in result["next_steps"][0]
    assert "non-dev deployed beta key" in "\n".join(result["next_steps"])


def test_launch_preflight_blocks_identical_staging_and_prod_urls(monkeypatch):
    import scripts.launch_preflight as lp

    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "https://hub.example.com/")
    monkeypatch.setenv("PROD_BASE_URL", "https://hub.example.com")
    monkeypatch.setenv("BETA_KEY", "ops-beta-key")
    monkeypatch.setattr(lp.httpx, "get", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("no probe")))

    result = lp.run_launch_preflight()

    assert result["ready"] is False
    assert result["failure_bucket"] == "operator_input_invalid"
    assert result["transport_checked"] is False
    assert result["operator_input_errors"] == ["STAGING_BASE_URL:must_differ_from_PROD_BASE_URL"]


def test_launch_preflight_blocks_provider_http_error(monkeypatch, tmp_path):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PROD_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("BETA_KEY", "ops-beta-key")
    monkeypatch.setattr(lp.httpx, "get", lambda *args, **kwargs: _FakeResponse(status_code=401))

    result = lp.run_launch_preflight()

    assert result["ready"] is False
    assert result["failure_bucket"] == "transport_or_provider"
    assert result["transport_checked"] is True
    assert result["transport_ok"] is True
    assert result["probe_status_code"] == 401


def test_launch_preflight_main_writes_reports(monkeypatch, tmp_path, capsys):
    import scripts.launch_preflight as lp

    monkeypatch.setattr(lp, "ROOT", tmp_path)
    monkeypatch.setenv("EMAILDJ_REAL_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("STAGING_BASE_URL", "https://staging.example.com")
    monkeypatch.setenv("PROD_BASE_URL", "https://prod.example.com")
    monkeypatch.setenv("BETA_KEY", "ops-beta-key")
    monkeypatch.setattr(lp.httpx, "get", lambda *args, **kwargs: _FakeResponse(status_code=200))
    monkeypatch.setattr(sys, "argv", ["launch_preflight.py"])

    exit_code = lp.main()
    captured = capsys.readouterr()
    payload = json.loads((tmp_path / "reports" / "launch" / "preflight.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["ready"] is True
    assert payload["operator_input_sources"]["BETA_KEY"]["explicit_env_present"] is True
    assert '"ready": true' in captured.out
    markdown = (tmp_path / "reports" / "launch" / "preflight.md").read_text(encoding="utf-8")
    assert "## Deployment Discovery Context" in markdown
    assert "## Web App Probe Context" in markdown
