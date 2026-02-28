"""
Redis Client — singleton async connection with connection pooling.

IMPLEMENTATION INSTRUCTIONS:
Exports: get_redis() → redis.asyncio.Redis

1. Use redis.asyncio.Redis (async client, not blocking).
2. Singleton pattern: create ONE Redis instance at module load time, reuse across
   all requests. Do NOT create a new connection per request — this would exhaust
   the connection pool.
3. Connection pooling config:
   - max_connections=20
   - socket_keepalive=True
   - socket_connect_timeout=5
   - decode_responses=True (return str, not bytes)
4. Initialize from env var:
   from redis.asyncio import Redis, ConnectionPool
   pool = ConnectionPool.from_url(
     os.environ["REDIS_URL"],
     max_connections=20,
     decode_responses=True,
   )
   _redis = Redis(connection_pool=pool)
5. get_redis(): return _redis (the singleton).
6. Usage pattern in other modules:
   redis = get_redis()
   await redis.hset("vault:{account_id}", "data", json_str)
   await redis.expire("vault:{account_id}", 3600)
7. Redis keys used across the system (for reference):
   - vault:{account_id}           → AccountContext JSON (TTL 1hr)
   - cost_tier1:{account_id}      → float, monthly cost counter
   - cost_tier2:{account_id}      → float, monthly cost counter
   - cost_tier3:{account_id}      → float, monthly cost counter
   - throttle_alerted:{account_id} → flag (TTL 24hr)
   - sdr_assignments:{sdr_id}     → Redis Set of assignment IDs
   - new_assignments_flag:{sdr_id} → flag (TTL 1hr)
   - research_job:{job_id}        → job state dict
   - deep_research_rate:{account_id} → sliding window counter
"""

import os
from redis.asyncio import Redis, ConnectionPool

_pool: ConnectionPool | None = None
_redis: Redis | None = None


def get_redis() -> Redis:
    # TODO: implement singleton init per instructions above
    global _pool, _redis
    if _redis is None:
        _pool = ConnectionPool.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            max_connections=20,
            decode_responses=True,
        )
        _redis = Redis(connection_pool=_pool)
    return _redis
