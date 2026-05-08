# Backend Architecture

Source: `hub-api/` — FastAPI hub, orchestration, generation, compliance.

---

## App Factory & Startup

Entry point: `hub-api/main.py`

On startup (`lifespan`):
1. `load_dotenv()` — load `.env`
2. `_validate_env()` — fail fast on bad config (mode, provider, launch mode, enforcement level, sample rate, API keys, pinned origins, and durable launch infra)
3. `init_engine()` — init Postgres engine
4. `get_redis().ping()` — assert Redis is reachable
5. Mount routers + middleware stack

**Startup is strict**: the app refuses to start with invalid config rather than silently degrading.
`limited_rollout` and `broad_launch` also require pinned `WEB_APP_ORIGIN`, pinned
`CHROME_EXTENSION_ORIGIN`, non-dev `EMAILDJ_WEB_BETA_KEYS`, explicit rate limit,
real provider mode, managed Redis/Postgres, and `VECTOR_STORE_BACKEND=pgvector`.

---

## Middleware Stack (applied in reverse order)

```
Request → CORSMiddleware → WebBetaAccessMiddleware → PiiRedactionMiddleware → CostGuardMiddleware → router
```

| Middleware | File | Purpose |
|---|---|---|
| CORS | FastAPI built-in | Allow-list: localhost:5173/5174, CHROME_EXTENSION_ORIGIN, WEB_APP_ORIGIN |
| WebBetaAccess | `api/middleware/beta_access.py` | Gate web endpoints behind EMAILDJ_WEB_BETA_KEYS |
| PiiRedaction | `api/middleware/pii_redaction.py` | Presidio NER scrub of request payloads |
| CostGuard | `api/middleware/cost_guard.py` | Monthly cost ceiling enforcement |

---

## Router Prefixes

| Prefix | Router file | Tags | Purpose |
|---|---|---|---|
| `/generate` | `api/routes/quick_generate.py` | generate | Extension quick-generate flow |
| `/research` | `api/routes/deep_research.py` | research | Async deep research jobs |
| `/web/v1` | `api/routes/web_mvp.py` | web-mvp | Web app generate/remix/stream/presets |
| `/web/v1/debug/config` | `api/routes/web_mvp.py` | web-mvp | Runtime launch config/debug probe for web endpoints |
| `/web/v1/debug/eval` | `api/routes/web_mvp.py` | web-mvp | Latest eval/launch debug report |
| `/campaigns` | `api/routes/campaigns.py` | campaigns | Campaign management |
| `/assignments` | `api/routes/assignments.py` | assignments | Prospect assignment |
| `/vault` | `api/routes/context_vault.py` | vault | Context vault ingest/prefetch/retrieve |
| `/webhooks` | `api/routes/webhooks.py` | webhooks | Edit/send/reply event ingestion |
| `/debug/config` | `main.py` | — | Runtime launch config/debug probe for root service checks |
| `/` | `main.py` | — | Health check: `GET /` → `{status: ok}` |

Full endpoint inventory: `docs/contracts/openapi_summary.md`

---

## Generation Pipeline

```
QuickGenerateRequest / WebGenerateRequest
  → PII precheck (middleware)
  → Context vault lookup (Redis cache → Postgres → Pinecone)
  → LangGraph agent graph (agents/graph.py)
      → generation_plan node
      → deep_research node (optional)
      → generate node (model_cascade.py → LLM provider)
      → output_enforcement node (compliance_rules.py + validate_ctco_output)
      → repair loop (if violations + repair mode)
  → SSE stream (streaming.py → EventSourceResponse)
```

See `docs/contracts/streaming_sse.md` for SSE event schema.

---

## Model Cascade (`email_generation/model_cascade.py`)

Tried in order until one succeeds:

| Tier | Providers | Models |
|---|---|---|
| 1 | openai, anthropic | GPT-4o, Claude Opus |
| 2 | openai, anthropic | GPT-4o-mini, Claude Haiku |
| 3 | groq | Llama 3.3 |

Controlled by `EMAILDJ_REAL_PROVIDER` (preferred provider) and `EMAILDJ_QUICK_GENERATE_MODE` (mock/real).
In launch modes, `USE_PROVIDER_STUB=1` is blocked; runtime reports must show
`effective_provider_source=external_provider`.

---

## Schemas (`api/schemas.py`)

All Pydantic request/response models. Key models:

| Model | Direction | Used by |
|---|---|---|
| `QuickGenerateRequest` | Request | `/generate` |
| `WebGenerateRequest` | Request | `/web/v1/generate` |
| `WebRemixRequest` | Request | `/web/v1/remix` |
| `WebPresetPreviewBatchRequest` | Request | `/web/v1/preset-previews/batch` |
| `WebGenerateAccepted` | Response | `/web/v1/generate` |
| `WebPresetPreviewBatchResponse` | Response | `/web/v1/preset-previews/batch` |
| `WebPreviewBatchMeta` | Embedded | Batch response metadata |

Full schema field tables: `docs/contracts/schemas.md`

---

## PII Layer (`pii/`)

3-layer defense-in-depth:

1. **Regex prefilter** (browser-side, extension) — strips obvious PII before HTTP call.
2. **Presidio NER** (`pii/presidio_redactor.py`) — server-side NLP entity recognition.
3. **Token vault** (`pii/token_vault.py`) — replaces entities with reversible tokens before LLM calls; restores in output.

---

## Context Vault (`context_vault/`)

Enriched prospect context cache:
- **Redis** (TTL: `CONTEXT_VAULT_CACHE_TTL_SECONDS`, default 3600s) — fast lookup
- **Postgres** (`infra/db.py`) — durable storage
- **Pinecone** (`infra/vector_store.py`) — semantic similarity search

Key modules: `cache.py` (Redis ops), `embedder.py` (vector embed), `extractor.py` (CRM extraction), `merger.py` (data merge), `models.py` (data models).
