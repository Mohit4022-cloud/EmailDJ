"""Redis-backed context cache with local-memory DB fallback."""

from __future__ import annotations

from typing import Optional

from context_vault.models import AccountContext
from infra.redis_client import get_redis
from infra import vector_store

_DB: dict[str, str] = {}


async def get_or_fetch(account_id: str) -> Optional[AccountContext]:
    redis = get_redis()
    key = f"vault:{account_id}"
    cached = await redis.hget(key, "data")
    if cached:
        return AccountContext.model_validate_json(cached)

    db_row = _DB.get(account_id)
    if db_row:
        await redis.hset(key, mapping={"data": db_row})
        await redis.expire(key, 3600)
        return AccountContext.model_validate_json(db_row)
    return None


async def set(account_id: str, context: AccountContext) -> None:
    json_str = context.model_dump_json()
    _DB[account_id] = json_str
    redis = get_redis()
    key = f"vault:{account_id}"
    await redis.hset(key, mapping={"data": json_str})
    await redis.expire(key, 3600)


async def invalidate(account_id: str) -> None:
    _DB.pop(account_id, None)
    redis = get_redis()
    await redis.delete(f"vault:{account_id}")
    await vector_store.delete(account_id)
