from __future__ import annotations


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
