# Data & State Architecture

How EmailDJ stores, caches, and expires data across a request lifecycle.

---

## Storage Layers

| Layer | Technology | TTL / Retention | Purpose |
|---|---|---|---|
| Redis | `hub-api/infra/redis_client.py` | Configurable per key | Session cache, context vault, request state |
| Postgres | `hub-api/infra/db.py` | Durable | Long-term context storage, audit log |
| Pinecone (or pgvector) | `hub-api/infra/vector_store.py` | Durable | Semantic context retrieval |
| Chrome storage | Extension | Browser-managed | Extension UI state, cached drafts |

For `limited_rollout` and `broad_launch`, Redis/Postgres/vector state must be
durable. The launch checks block `REDIS_FORCE_INMEMORY=1`, local SQLite/default
database URLs, and `VECTOR_STORE_BACKEND=memory`. The launch-ready state is
managed Redis via `REDIS_URL`, managed Postgres via `DATABASE_URL`, and
`VECTOR_STORE_BACKEND=pgvector`.

---

## Key Data Maps

### Context Vault (Redis → Postgres → Pinecone/pgvector)

```
Key pattern : vault:{account_id}
TTL         : CONTEXT_VAULT_CACHE_TTL_SECONDS (default: 3600s = 1hr)
Contents    : EnrichedProspectContext (CRM data, intent signals, activity timeline)
Fallback    : On Redis miss → Postgres lookup → vector semantic search
Write path  : POST /vault/ingest (VaultIngestRequest)
Read path   : Internal during generate/remix (context_vault/cache.py)
Prefetch    : POST /vault/prefetch (VaultPrefetchRequest) — warms cache for account list
```

### Generation Session (Redis)

```
Key pattern : session:{session_id}
TTL         : Implicit (cleared after QUICK_REQUEST_TTL_SECONDS = 300s for quick generate)
Contents    : Original WebGenerateRequest + draft history + style_profile
Write path  : POST /web/v1/generate
Read path   : POST /web/v1/remix (requires session_id), GET /web/v1/stream/{request_id}
Purpose     : Enables remix without re-sending full payload
```

### Quick Generate Request State (Redis)

```
Key pattern : request:{request_id}
TTL         : QUICK_REQUEST_TTL_SECONDS (default: 300s)
Contents    : Generation status, output buffer, metadata
Write path  : POST /generate
Read path   : GET stream endpoint (SSE stream consumer)
```

### Deep Research Job (Redis)

```
Key pattern : research:{job_id}
TTL         : DEEP_RESEARCH_JOB_TTL_SECONDS (default: 86400s = 24hr)
Contents    : Job status, raw research results
Rate limit  : DEEP_RESEARCH_RATE_LIMIT_PER_HOUR (default: 200)
```

---

## Request Lifecycle State Diagram

```
POST /web/v1/generate
  → save_session(session_id, payload)         [Redis: session:{id}]
  → vault lookup(account_id)                  [Redis → Postgres → Pinecone]
  → create request_ticket(request_id)         [Redis: request:{id}]
  → return {request_id, session_id}

GET /web/v1/stream/{request_id}
  → load request_ticket(request_id)           [Redis]
  → build_draft(session, style_profile)       [in-memory]
  → stream tokens                             [SSE]
  → on done: update request_ticket status     [Redis]

POST /web/v1/remix
  → load_session(session_id)                  [Redis]
  → re-run build_draft with new style_profile [in-memory]
  → stream tokens                             [SSE]
```

---

## Retention Notes

- No email draft content is persisted to Postgres by default. Drafts are ephemeral —
  they exist in Redis for the request TTL, then are gone.
- Context vault is the only long-lived store of prospect data. It is cleared by TTL,
  not by explicit delete (unless a vault invalidate endpoint exists).
- PII defense (token vault) replaces raw PII with tokens before any data touches the
  LLM. The token-to-PII mapping is in-process only; it is not persisted.

---

## Launch Runtime Snapshots

`make launch-verify-deployed` captures staging and production runtime snapshots
under `hub-api/reports/launch/runtime_snapshots/`. Those snapshots are the
source of truth for proving durable state, pinned origins, provider mode, route
gates, and release fingerprint parity in launch checks.

## Redis Force-InMemory (CI / Test)

Set `REDIS_FORCE_INMEMORY=1` to use a lightweight in-memory Redis shim.
Used in CI to avoid requiring a real Redis instance for unit/integration tests.
This setting is never launch-ready and is reported as
`redis_not_durable_for_launch_mode` in launch modes.
