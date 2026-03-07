import os

import pytest


def _base_env():
    return {
        "CHROME_EXTENSION_ORIGIN": "chrome-extension://dev",
        "USE_PROVIDER_STUB": "1",
        "EMAILDJ_REAL_PROVIDER": "openai",
        "EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL": "repair",
        "EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE": "0.01",
        "EMAILDJ_PRESET_PREVIEW_PIPELINE": "off",
        "APP_ENV": "test",
    }


def _apply_env(monkeypatch, values: dict[str, str]):
    for key in list(os.environ.keys()):
        if key.startswith("EMAILDJ_") or key.startswith("FEATURE_") or key in {
            "USE_PROVIDER_STUB",
            "DEV_ALLOW_P0_OFF",
            "APP_ENV",
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
    env["USE_PROVIDER_STUB"] = "0"
    env["EMAILDJ_REAL_PROVIDER"] = "openai"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="requires OPENAI_API_KEY"):
        _validate_env()


def test_validate_env_accepts_real_mode_with_provider_key(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["USE_PROVIDER_STUB"] = "0"
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


def test_validate_env_rejects_invalid_launch_mode(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["EMAILDJ_LAUNCH_MODE"] = "ship_it"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="Invalid EMAILDJ_LAUNCH_MODE"):
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


def test_validate_env_dev_fails_when_p0_disabled_without_override(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "development"
    env["USE_PROVIDER_STUB"] = "0"
    env["OPENAI_API_KEY"] = "test-key"
    env["FEATURE_PERSONA_ROUTER_GLOBAL"] = "0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="Dev must run with P0 features enabled"):
        _validate_env()


def test_validate_env_dev_allows_p0_override(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "development"
    env["USE_PROVIDER_STUB"] = "0"
    env["OPENAI_API_KEY"] = "test-key"
    env["FEATURE_PERSONA_ROUTER_GLOBAL"] = "0"
    env["DEV_ALLOW_P0_OFF"] = "1"
    _apply_env(monkeypatch, env)

    _validate_env()
