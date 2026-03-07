from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    def __init__(self):
        self._data: dict[str, CacheEntry[T]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.time():
                self._data.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: T, ttl_seconds: int) -> None:
        async with self._lock:
            self._data[key] = CacheEntry(value=value, expires_at=time.time() + max(1, ttl_seconds))

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()

