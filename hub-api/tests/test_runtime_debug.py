from __future__ import annotations

from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_runtime_debug_surfaces_local_infra_defaults(monkeypatch):
    import runtime_debug

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "dev")
    monkeypatch.delenv("REDIS_FORCE_INMEMORY", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("VECTOR_STORE_BACKEND", raising=False)

    payload = runtime_debug.build_runtime_debug_payload()

    assert payload["redis_config_state"] == "default_local_redis"
    assert payload["database_config_state"] == "default_local_sqlite"
    assert payload["vector_store_config_state"] == "memory_backend"
    assert payload["vector_store_backend"] == "memory"
    assert payload["validation_fallback_allowed"] is True
    assert payload["validation_fallback_policy"] == "dev_only_fail_closed_in_launch_modes"


def test_runtime_debug_surfaces_external_infra_config(monkeypatch):
    import runtime_debug

    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("EMAILDJ_LAUNCH_MODE", "limited_rollout")
    monkeypatch.delenv("REDIS_FORCE_INMEMORY", raising=False)
    monkeypatch.setenv("REDIS_URL", "rediss://cache.emaildj.test:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://db.example/emaildj")
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "pgvector")

    payload = runtime_debug.build_runtime_debug_payload()

    assert payload["redis_config_state"] == "external_redis_configured"
    assert payload["database_config_state"] == "external_postgres_configured"
    assert payload["vector_store_config_state"] == "pgvector_configured"
    assert payload["vector_store_backend"] == "pgvector"
    assert payload["validation_fallback_allowed"] is False


def test_runtime_debug_uses_render_git_commit_as_release_fingerprint(monkeypatch):
    import runtime_debug

    monkeypatch.delenv("EMAILDJ_GIT_SHA", raising=False)
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    monkeypatch.setenv("RENDER_GIT_COMMIT", "rendercommit123")
    monkeypatch.setattr(runtime_debug, "_git_sha_from_repo", lambda: None)

    fields = runtime_debug._release_fingerprint_fields()

    assert fields["git_sha"] == "rendercommit123"
    assert runtime_debug._release_fingerprint(fields) == "git_sha=rendercommit123"
