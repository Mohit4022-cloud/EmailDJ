from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _runtime_payload(**overrides) -> dict:
    payload = {
        "generated_at_utc": "2026-03-08T18:30:00Z",
        "launch_mode": "limited_rollout",
        "runtime_mode": "real",
        "provider_stub_enabled": False,
        "real_provider_preference": "openai",
        "effective_provider_source": "external_provider",
        "effective_quick_generate_mode": "real",
        "route_gates": {"generate": True, "remix": True, "preview": False},
        "route_gate_sources": {"generate": "launch_mode:limited_rollout", "remix": "launch_mode:limited_rollout", "preview": "launch_mode:limited_rollout"},
        "preview_pipeline_enabled": False,
        "release_fingerprint_available": True,
        "release_fingerprint": "git_sha=abc123def456",
        "git_sha": "abc123def456",
        "build_id": None,
        "image_tag": None,
        "release_version": None,
        "chrome_extension_origin_state": "explicit_pinned",
        "web_app_origin_state": "explicit_pinned",
        "beta_keys_state": "explicit_pinned",
        "web_rate_limit_per_min": 300,
        "web_rate_limit_source": "explicit_env",
        "effective_provider": "openai",
        "effective_model": "gpt-5-nano",
        "effective_model_identifier": "openai/gpt-5-nano",
        "app_env": "staging",
    }
    payload.update(overrides)
    return payload


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, payload: object | None = None, json_error: Exception | None = None):
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


def test_capture_runtime_snapshot_writes_explicit_output_and_metadata(monkeypatch, tmp_path):
    import scripts.capture_runtime_snapshot as csr

    captured: dict[str, object] = {}

    def fake_get(url, headers, timeout, follow_redirects):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        captured["follow_redirects"] = follow_redirects
        return _FakeResponse(payload=_runtime_payload())

    monkeypatch.setattr(csr.httpx, "get", fake_get)
    output = tmp_path / "snapshot.json"

    result = csr.capture_runtime_snapshot(
        url="https://staging.example.com",
        label="staging",
        output=str(output),
        headers=["x-emaildj-beta-key: secret"],
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert result["output"] == str(output)
    assert captured["url"] == "https://staging.example.com/web/v1/debug/config?endpoint=generate&bucket_key=rollout-audit"
    assert captured["headers"] == {"x-emaildj-beta-key": "secret"}
    assert saved["captured_at_utc"]
    assert saved["source_url"] == captured["url"]
    assert saved["label"] == "staging"
    assert saved["launch_mode"] == "limited_rollout"


@pytest.mark.parametrize(
    ("label", "expected_name"),
    [
        ("staging", "staging.json"),
        ("production", "production.json"),
    ],
)
def test_capture_runtime_snapshot_uses_default_output_for_standard_labels(monkeypatch, tmp_path, label, expected_name):
    import scripts.capture_runtime_snapshot as csr

    monkeypatch.setattr(csr, "ROOT", tmp_path)
    monkeypatch.setattr(
        csr,
        "DEFAULT_OUTPUTS",
        {
            "staging": tmp_path / "reports" / "launch" / "runtime_snapshots" / "staging.json",
            "production": tmp_path / "reports" / "launch" / "runtime_snapshots" / "production.json",
        },
    )
    monkeypatch.setattr(csr.httpx, "get", lambda *args, **kwargs: _FakeResponse(payload=_runtime_payload()))

    result = csr.capture_runtime_snapshot(url="https://example.com", label=label)

    output_path = Path(result["output"])
    assert output_path.name == expected_name
    assert output_path.exists()


def test_capture_runtime_snapshot_rejects_invalid_json(monkeypatch, tmp_path):
    import scripts.capture_runtime_snapshot as csr

    monkeypatch.setattr(
        csr.httpx,
        "get",
        lambda *args, **kwargs: _FakeResponse(json_error=ValueError("bad json")),
    )
    output = tmp_path / "snapshot.json"

    with pytest.raises(RuntimeError, match="invalid_json:https://prod.example.com/web/v1/debug/config\\?endpoint=generate&bucket_key=rollout-audit:bad json"):
        csr.capture_runtime_snapshot(url="https://prod.example.com", label="production", output=str(output))

    assert not output.exists()


def test_capture_runtime_snapshot_rejects_non_200(monkeypatch, tmp_path):
    import scripts.capture_runtime_snapshot as csr

    monkeypatch.setattr(csr.httpx, "get", lambda *args, **kwargs: _FakeResponse(status_code=503, payload={}))
    output = tmp_path / "snapshot.json"

    with pytest.raises(RuntimeError, match="non_200_response:503:https://prod.example.com/web/v1/debug/config\\?endpoint=generate&bucket_key=rollout-audit"):
        csr.capture_runtime_snapshot(url="https://prod.example.com", label="production", output=str(output))

    assert not output.exists()


def test_capture_runtime_snapshot_rejects_missing_critical_fields(monkeypatch, tmp_path):
    import scripts.capture_runtime_snapshot as csr

    payload = _runtime_payload()
    del payload["effective_provider_source"]
    monkeypatch.setattr(csr.httpx, "get", lambda *args, **kwargs: _FakeResponse(payload=payload))
    output = tmp_path / "snapshot.json"

    with pytest.raises(RuntimeError, match="schema_incomplete:effective_provider_source"):
        csr.capture_runtime_snapshot(url="https://prod.example.com", label="production", output=str(output))

    assert not output.exists()


def test_capture_runtime_snapshot_warns_on_missing_recommended_fields_and_still_writes(monkeypatch, tmp_path, capsys):
    import scripts.capture_runtime_snapshot as csr

    payload = _runtime_payload()
    del payload["preview_pipeline_enabled"]
    monkeypatch.setattr(csr.httpx, "get", lambda *args, **kwargs: _FakeResponse(payload=payload))
    output = tmp_path / "snapshot.json"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capture_runtime_snapshot.py",
            "--url",
            "https://prod.example.com",
            "--label",
            "production",
            "--output",
            str(output),
        ],
    )
    exit_code = csr.main()
    captured = capsys.readouterr()

    assert exit_code == 0
    assert output.exists()
    assert "warning: missing recommended runtime fields: preview_pipeline_enabled" in captured.err


def test_capture_runtime_snapshot_preserves_full_debug_config_url(monkeypatch, tmp_path):
    import scripts.capture_runtime_snapshot as csr

    seen: dict[str, object] = {}

    def fake_get(url, headers, timeout, follow_redirects):  # noqa: ANN001
        seen["url"] = url
        return _FakeResponse(payload=_runtime_payload())

    monkeypatch.setattr(csr.httpx, "get", fake_get)
    output = tmp_path / "snapshot.json"

    csr.capture_runtime_snapshot(
        url="https://prod.example.com/web/v1/debug/config?endpoint=preview&bucket_key=custom",
        label="production",
        output=str(output),
    )

    assert seen["url"] == "https://prod.example.com/web/v1/debug/config?endpoint=preview&bucket_key=custom"


def test_capture_runtime_snapshot_requires_output_for_custom_label():
    import scripts.capture_runtime_snapshot as csr

    with pytest.raises(ValueError, match="label 'canary' requires --output"):
        csr.capture_runtime_snapshot(url="https://prod.example.com", label="canary")
