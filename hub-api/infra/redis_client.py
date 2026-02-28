"""Redis singleton client with in-memory fallback."""

from __future__ import annotations

import logging
import os
from time import time

logger = logging.getLogger(__name__)

try:
    from redis.asyncio import ConnectionPool, Redis
except Exception:  # pragma: no cover
    ConnectionPool = None  # type: ignore[assignment]
    Redis = None  # type: ignore[assignment]


class InMemoryRedis:
    def __init__(self):
        self.data: dict[str, str] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.sets: dict[str, set[str]] = {}
        self.expires: dict[str, float] = {}

    def _expired(self, key: str) -> bool:
        exp = self.expires.get(key)
        return exp is not None and exp <= time()

    def _check_exp(self, key: str) -> None:
        if self._expired(key):
            self.data.pop(key, None)
            self.hashes.pop(key, None)
            self.sets.pop(key, None)
            self.expires.pop(key, None)

    async def ping(self):
        return True

    async def close(self):
        return None

    async def get(self, key):
        self._check_exp(key)
        return self.data.get(key)

    async def set(self, key, value):
        self.data[key] = str(value)

    async def setex(self, key, ttl, value):
        self.data[key] = str(value)
        self.expires[key] = time() + ttl

    async def delete(self, key):
        self.data.pop(key, None)
        self.hashes.pop(key, None)
        self.sets.pop(key, None)
        self.expires.pop(key, None)

    async def hget(self, key, field):
        self._check_exp(key)
        return self.hashes.get(key, {}).get(field)

    async def hset(self, key, mapping=None, **kwargs):
        self.hashes.setdefault(key, {})
        data = mapping or kwargs
        for k, v in data.items():
            self.hashes[key][k] = str(v)

    async def expire(self, key, ttl):
        self.expires[key] = time() + ttl

    async def sadd(self, key, *values):
        self.sets.setdefault(key, set())
        self.sets[key].update(str(v) for v in values)

    async def srem(self, key, *values):
        self.sets.setdefault(key, set())
        for v in values:
            self.sets[key].discard(str(v))

    async def smembers(self, key):
        return self.sets.get(key, set())


_pool = None
_redis = None
_warned_inmemory = False


def get_redis():
    global _pool, _redis, _warned_inmemory
    if _redis is not None:
        return _redis

    if os.environ.get("REDIS_FORCE_INMEMORY", "0") == "1":
        _redis = InMemoryRedis()
        if not _warned_inmemory:
            logger.warning("redis_fallback_inmemory_active")
            _warned_inmemory = True
        return _redis

    if Redis is None or ConnectionPool is None:
        _redis = InMemoryRedis()
        if not _warned_inmemory:
            logger.warning("redis_fallback_inmemory_active")
            _warned_inmemory = True
        return _redis

    _pool = ConnectionPool.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        max_connections=20,
        decode_responses=True,
        socket_keepalive=True,
        socket_connect_timeout=5,
    )
    _redis = Redis(connection_pool=_pool)
    return _redis


async def close_redis() -> None:
    global _pool, _redis
    if _redis is not None and hasattr(_redis, "close"):
        await _redis.close()
    _redis = None
    if _pool is not None and hasattr(_pool, "disconnect"):
        await _pool.disconnect()
    _pool = None
