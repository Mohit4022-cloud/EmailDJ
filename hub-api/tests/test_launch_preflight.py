from __future__ import annotations

import json
from pathlib import Path
import sys

import httpx

sys.path.append(str(Path(__file__).resolve().parents[1]))


class _FakeResponse:
    def __init__(self, status_code: int = 200):
        self.status_code = status_code


def test_launch_preflight_blocks_missing_inputs_without_transport_probe(monkeypatch):
    import scripts.launch_preflight as lp

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


def test_launch_preflight_blocks_transport_failure(monkeypatch):
    import scripts.launch_preflight as lp

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


def test_launch_preflight_blocks_provider_http_error(monkeypatch):
    import scripts.launch_preflight as lp

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
    assert '"ready": true' in captured.out
    assert (tmp_path / "reports" / "launch" / "preflight.md").exists()
