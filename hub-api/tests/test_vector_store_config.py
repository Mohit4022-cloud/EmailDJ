from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_vector_store_backend_is_resolved_at_call_time(monkeypatch):
    import infra.vector_store as vector_store

    vector_store._MEM.clear()
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "memory")

    await vector_store.upsert("acct-1", [1.0, 0.0], {"name": "Acme"})
    matches = await vector_store.query([1.0, 0.0], top_k=1)

    assert matches[0].account_id == "acct-1"
    assert matches[0].metadata == {"name": "Acme"}

    captured: dict[str, object] = {}

    async def fake_pg_upsert(*, account_id: str, embedding: list, metadata: dict) -> None:
        captured["account_id"] = account_id
        captured["embedding"] = embedding
        captured["metadata"] = metadata

    monkeypatch.setattr(vector_store, "_pg_upsert", fake_pg_upsert)
    monkeypatch.setenv("VECTOR_STORE_BACKEND", "pgvector")

    await vector_store.upsert("acct-2", [0.0, 1.0], {"name": "Beta"})

    assert captured == {
        "account_id": "acct-2",
        "embedding": [0.0, 1.0],
        "metadata": {"name": "Beta"},
    }
