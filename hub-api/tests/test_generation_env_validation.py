import os

import pytest


def _base_env():
    return {
        "CHROME_EXTENSION_ORIGIN": "chrome-extension://dev",
        "EMAILDJ_QUICK_GENERATE_MODE": "mock",
        "EMAILDJ_REAL_PROVIDER": "openai",
        "EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL": "repair",
        "EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE": "0.01",
        "EMAILDJ_PRESET_PREVIEW_PIPELINE": "off",
    }


def _apply_env(monkeypatch, values: dict[str, str]):
    for key in list(os.environ.keys()):
        if key.startswith("EMAILDJ_") or key in {
            "CHROME_EXTENSION_ORIGIN",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "GROQ_API_KEY",
        }:
            monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_validate_env_rejects_real_mode_without_provider_key(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["EMAILDJ_QUICK_GENERATE_MODE"] = "real"
    env["EMAILDJ_REAL_PROVIDER"] = "openai"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="requires OPENAI_API_KEY"):
        _validate_env()


def test_validate_env_accepts_real_mode_with_provider_key(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["EMAILDJ_QUICK_GENERATE_MODE"] = "real"
    env["EMAILDJ_REAL_PROVIDER"] = "openai"
    env["OPENAI_API_KEY"] = "test-key"
    _apply_env(monkeypatch, env)

    _validate_env()


def test_validate_env_rejects_invalid_provider(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["EMAILDJ_REAL_PROVIDER"] = "not-a-provider"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="Invalid EMAILDJ_REAL_PROVIDER"):
        _validate_env()


def test_validate_env_rejects_invalid_enforcement_level(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL"] = "strictest"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="Invalid EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL"):
        _validate_env()


def test_validate_env_rejects_invalid_debug_sample_rate(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE"] = "1.5"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE"):
        _validate_env()
