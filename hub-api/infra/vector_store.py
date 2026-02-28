"""Vector store abstraction with in-memory fallback."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

VECTOR_STORE_BACKEND = os.environ.get("VECTOR_STORE_BACKEND", "memory")


@dataclass
class Match:
    account_id: str
    score: float
    metadata: dict


_MEM: dict[str, tuple[list[float], dict]] = {}


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
    # MVP keeps a local-memory backend to avoid infra coupling in dev.
    _MEM[account_id] = (list(embedding), dict(metadata))


async def query(embedding: list, top_k: int = 10) -> list[Match]:
    scored: list[Match] = []
    for account_id, (vec, metadata) in _MEM.items():
        scored.append(Match(account_id=account_id, score=_cosine(embedding, vec), metadata=metadata))
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:top_k]


async def delete(account_id: str) -> None:
    _MEM.pop(account_id, None)
