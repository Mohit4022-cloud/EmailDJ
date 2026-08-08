"""Vector store abstraction with local-memory dev mode and durable launch mode."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

try:
    from sqlalchemy import text
except Exception:  # pragma: no cover
    text = None  # type: ignore[assignment]

from infra import db


@dataclass
class Match:
    account_id: str
    score: float
    metadata: dict


_MEM: dict[str, tuple[list[float], dict]] = {}
_PG_TABLE_READY_ENGINE_ID: int | None = None


def _backend() -> str:
    return (os.environ.get("VECTOR_STORE_BACKEND") or "memory").strip().lower() or "memory"


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def upsert(account_id: str, embedding: list, metadata: dict) -> None:
    if _backend() == "pgvector":
        await _pg_upsert(account_id=account_id, embedding=embedding, metadata=metadata)
        return

    # Dev keeps a local-memory backend to avoid infra coupling.
    _MEM[account_id] = (list(embedding), dict(metadata))


async def query(embedding: list, top_k: int = 10) -> list[Match]:
    if _backend() == "pgvector":
        return await _pg_query(embedding=embedding, top_k=top_k)

    scored: list[Match] = []
    for account_id, (vec, metadata) in _MEM.items():
        scored.append(Match(account_id=account_id, score=_cosine(embedding, vec), metadata=metadata))
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:top_k]


async def delete(account_id: str) -> None:
    if _backend() == "pgvector":
        await _pg_delete(account_id)
        return

    _MEM.pop(account_id, None)


def _require_pg_support() -> None:
    if text is None:
        raise RuntimeError("VECTOR_STORE_BACKEND=pgvector requires SQLAlchemy.")
    db.init_engine()
    if db.engine is None:
        raise RuntimeError("VECTOR_STORE_BACKEND=pgvector requires a configured database engine.")


async def _ensure_pg_table() -> None:
    global _PG_TABLE_READY_ENGINE_ID
    _require_pg_support()
    engine_id = id(db.engine)
    if _PG_TABLE_READY_ENGINE_ID == engine_id:
        return
    async with db.engine.begin() as conn:
        await conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS context_vector_store (
                    account_id TEXT PRIMARY KEY,
                    embedding TEXT NOT NULL,
                    metadata TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    _PG_TABLE_READY_ENGINE_ID = engine_id


async def _pg_upsert(*, account_id: str, embedding: list, metadata: dict) -> None:
    await _ensure_pg_table()
    async with db.engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO context_vector_store (account_id, embedding, metadata, updated_at)
                VALUES (:account_id, :embedding, :metadata, CURRENT_TIMESTAMP)
                ON CONFLICT (account_id)
                DO UPDATE SET
                    embedding = EXCLUDED.embedding,
                    metadata = EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "account_id": account_id,
                "embedding": json.dumps([float(value) for value in embedding]),
                "metadata": json.dumps(dict(metadata)),
            },
        )


async def _pg_query(*, embedding: list, top_k: int) -> list[Match]:
    await _ensure_pg_table()
    async with db.engine.connect() as conn:
        result = await conn.execute(text("SELECT account_id, embedding, metadata FROM context_vector_store"))
        rows = result.mappings().all()

    query_embedding = [float(value) for value in embedding]
    scored: list[Match] = []
    for row in rows:
        try:
            stored_embedding = json.loads(row["embedding"])
            metadata = json.loads(row["metadata"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        scored.append(
            Match(
                account_id=str(row["account_id"]),
                score=_cosine(query_embedding, [float(value) for value in stored_embedding]),
                metadata=dict(metadata),
            )
        )
    scored.sort(key=lambda match: match.score, reverse=True)
    return scored[:top_k]


async def _pg_delete(account_id: str) -> None:
    await _ensure_pg_table()
    async with db.engine.begin() as conn:
        await conn.execute(text("DELETE FROM context_vector_store WHERE account_id = :account_id"), {"account_id": account_id})
