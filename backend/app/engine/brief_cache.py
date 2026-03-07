from __future__ import annotations

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class CacheEntry:
    created_at: float
    value: dict[str, Any]


class BriefCache:
    def __init__(self, *, max_size: int = 200, ttl_seconds: int = 30 * 60):
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = max(60, int(ttl_seconds))
        self._items: OrderedDict[str, CacheEntry] = OrderedDict()

    def get(self, key: str) -> dict[str, Any] | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        now = time.time()
        if now - entry.created_at > self.ttl_seconds:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return dict(entry.value)

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._items[key] = CacheEntry(created_at=time.time(), value=dict(value))
        self._items.move_to_end(key)
        while len(self._items) > self.max_size:
            self._items.popitem(last=False)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_brief_cache_key(normalized_context: dict[str, Any]) -> str:
    stable = _stable_json(normalized_context)
    return hashlib.sha256(stable.encode("utf-8")).hexdigest()
