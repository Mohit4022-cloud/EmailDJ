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
            "WEB_APP_ORIGIN",
            "REDIS_FORCE_INMEMORY",
            "REDIS_URL",
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


def test_validate_env_prod_rejects_missing_web_app_origin(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "prod"
    env["EMAILDJ_WEB_BETA_KEYS"] = "ops-beta-key"
    env["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "300"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="WEB_APP_ORIGIN"):
        _validate_env()


def test_validate_env_prod_rejects_localhost_web_app_origin(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "prod"
    env["WEB_APP_ORIGIN"] = "http://localhost:5174"
    env["EMAILDJ_WEB_BETA_KEYS"] = "ops-beta-key"
    env["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "300"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="localhost"):
        _validate_env()


def test_validate_env_prod_rejects_missing_beta_keys(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "prod"
    env["WEB_APP_ORIGIN"] = "https://app.emaildj.test"
    env["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "300"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="EMAILDJ_WEB_BETA_KEYS"):
        _validate_env()


def test_validate_env_prod_rejects_dev_beta_key(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "prod"
    env["WEB_APP_ORIGIN"] = "https://app.emaildj.test"
    env["EMAILDJ_WEB_BETA_KEYS"] = "dev-beta-key"
    env["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "300"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="dev-beta-key"):
        _validate_env()


def test_validate_env_prod_rejects_missing_rate_limit(monkeypatch):
    from main import _validate_env

    env = _base_env()
    env["APP_ENV"] = "prod"
    env["WEB_APP_ORIGIN"] = "https://app.emaildj.test"
    env["EMAILDJ_WEB_BETA_KEYS"] = "ops-beta-key"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="EMAILDJ_WEB_RATE_LIMIT_PER_MIN"):
        _validate_env()


def _limited_rollout_env() -> dict[str, str]:
    env = _base_env()
    env["APP_ENV"] = "staging"
    env["EMAILDJ_LAUNCH_MODE"] = "limited_rollout"
    env["CHROME_EXTENSION_ORIGIN"] = "chrome-extension://emaildj-test"
    env["WEB_APP_ORIGIN"] = "https://app.emaildj.test"
    env["EMAILDJ_WEB_BETA_KEYS"] = "ops-beta-key"
    env["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "300"
    env["USE_PROVIDER_STUB"] = "0"
    env["OPENAI_API_KEY"] = "test-key"
    return env


def test_validate_env_limited_rollout_rejects_dev_chrome_origin(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["CHROME_EXTENSION_ORIGIN"] = "chrome-extension://dev"
    env["REDIS_URL"] = "rediss://cache.emaildj.test:6379/0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="CHROME_EXTENSION_ORIGIN"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_local_web_origin_outside_prod(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["APP_ENV"] = "test"
    env["WEB_APP_ORIGIN"] = "http://localhost:5174"
    env["REDIS_URL"] = "rediss://cache.emaildj.test:6379/0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="WEB_APP_ORIGIN"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_dev_beta_key_outside_prod(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["APP_ENV"] = "test"
    env["EMAILDJ_WEB_BETA_KEYS"] = "dev-beta-key"
    env["REDIS_URL"] = "rediss://cache.emaildj.test:6379/0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="dev-beta-key"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_provider_stub(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["USE_PROVIDER_STUB"] = "1"
    env["REDIS_URL"] = "rediss://cache.emaildj.test:6379/0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="real provider mode"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_preview_route_override(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["EMAILDJ_ROUTE_PREVIEW_ENABLED"] = "1"
    env["REDIS_URL"] = "rediss://cache.emaildj.test:6379/0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="preview route disabled"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_forced_inmemory_redis(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["REDIS_FORCE_INMEMORY"] = "1"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="REDIS_FORCE_INMEMORY"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_missing_redis_url(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        _validate_env()


def test_validate_env_limited_rollout_rejects_local_redis_url(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["REDIS_URL"] = "redis://localhost:6379/0"
    _apply_env(monkeypatch, env)

    with pytest.raises(RuntimeError, match="non-local"):
        _validate_env()


def test_validate_env_limited_rollout_accepts_external_redis(monkeypatch):
    from main import _validate_env

    env = _limited_rollout_env()
    env["REDIS_URL"] = "rediss://cache.emaildj.test:6379/0"
    _apply_env(monkeypatch, env)

    _validate_env()
