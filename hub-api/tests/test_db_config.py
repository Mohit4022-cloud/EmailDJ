from __future__ import annotations

import pytest


def test_init_engine_reads_database_url_at_call_time(monkeypatch):
    import infra.db as db

    calls: list[tuple[str, dict]] = []
    fake_engine = object()

    def fake_create_async_engine(url: str, **kwargs):
        calls.append((url, kwargs))
        return fake_engine

    def fake_sessionmaker(engine, *, expire_on_commit: bool):
        return {"engine": engine, "expire_on_commit": expire_on_commit}

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://db.emaildj.test/emaildj")
    monkeypatch.setattr(db, "engine", None)
    monkeypatch.setattr(db, "AsyncSessionLocal", None)
    monkeypatch.setattr(db, "create_async_engine", fake_create_async_engine)
    monkeypatch.setattr(db, "async_sessionmaker", fake_sessionmaker)

    db.init_engine()

    assert calls[0][0] == "postgresql+asyncpg://db.emaildj.test/emaildj"
    assert db.engine is fake_engine
    assert db.AsyncSessionLocal == {"engine": fake_engine, "expire_on_commit": False}


@pytest.mark.parametrize(
    ("raw_url", "expected_url"),
    [
        (
            "postgres://user:pass@db.emaildj.test:5432/emaildj",
            "postgresql+asyncpg://user:pass@db.emaildj.test:5432/emaildj",
        ),
        (
            "postgresql://user:pass@db.emaildj.test:5432/emaildj",
            "postgresql+asyncpg://user:pass@db.emaildj.test:5432/emaildj",
        ),
        (
            "postgresql+asyncpg://user:pass@db.emaildj.test:5432/emaildj",
            "postgresql+asyncpg://user:pass@db.emaildj.test:5432/emaildj",
        ),
        (
            "sqlite+aiosqlite:///./emaildj.db",
            "sqlite+aiosqlite:///./emaildj.db",
        ),
    ],
)
def test_normalize_async_database_url_for_render_connection_strings(raw_url, expected_url):
    import infra.db as db

    assert db._normalize_async_database_url(raw_url) == expected_url
