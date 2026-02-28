"""
Context Vault Cache — Redis-based caching for AccountContext.

IMPLEMENTATION INSTRUCTIONS:
Exports: get_or_fetch(account_id: str) → AccountContext | None
         set(account_id: str, context: AccountContext) → None
         invalidate(account_id: str) → None

get_or_fetch(account_id):
1. Try Redis first: HGET "vault:{account_id}" "data"
   - Target: <10ms cache hit.
   - Deserialize JSON → AccountContext.model_validate_json(cached_json).
   - If hit: return immediately.
2. On Redis miss: fetch from primary DB (PostgreSQL via infra.db).
   - Query: SELECT context_json FROM account_contexts WHERE account_id = ?
   - If found: populate Redis cache with TTL=3600s (SETEX key 3600 value).
   - Return AccountContext.
3. If neither: return None (caller handles missing context).
4. Pre-staging optimization: the extension sends a payload on every CRM navigation
   (before SDR clicks Generate). This triggers /vault/prefetch which calls
   get_or_fetch() to pre-warm the cache. By the time the SDR clicks Generate,
   the context is already in Redis. This is critical for the 2-second P95 budget.

set(account_id, context):
1. Serialize: json_str = context.model_dump_json()
2. HSET "vault:{account_id}" "data" json_str
3. EXPIRE "vault:{account_id}" 3600

invalidate(account_id):
1. DEL "vault:{account_id}"
2. Also invalidate from vector DB: call vector_store.delete(account_id) if stale.
"""

from typing import Optional
from context_vault.models import AccountContext


async def get_or_fetch(account_id: str) -> Optional[AccountContext]:
    # TODO: implement per instructions above
    return None


async def set(account_id: str, context: AccountContext) -> None:
    # TODO: implement per instructions above
    pass


async def invalidate(account_id: str) -> None:
    # TODO: implement per instructions above
    pass
