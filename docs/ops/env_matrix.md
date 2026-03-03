# Environment Matrix

Generated from `hub-api/.env.example` + repository env usage on **2026-03-02 18:03:18Z**.
Sweep-updated: **2026-03-02** (columns aligned to canonical format).

> **Note:** Never commit secrets to this file. Use `<redacted>` for secret values.
> `required? = conditional` means the var is required only when a dependent feature/provider is enabled.

---

## LLM Providers

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `OPENAI_API_KEY` | — | conditional | `email_generation/quick_generate.py`, `email_generation/preset_preview_pipeline.py`, CI nightly | `sk-fake-key-for-tests` | Required when `EMAILDJ_REAL_PROVIDER=openai` or preview pipeline is on |
| `ANTHROPIC_API_KEY` | — | conditional | `email_generation/quick_generate.py` | `sk-ant-fake` | Required when `EMAILDJ_REAL_PROVIDER=anthropic` |
| `GROQ_API_KEY` | — | conditional | `email_generation/quick_generate.py` | `gsk_fake` | Required when `EMAILDJ_REAL_PROVIDER=groq` |
| `EMAILDJ_REAL_PROVIDER` | `openai` | no | `email_generation/model_cascade.py`, `email_generation/quick_generate.py`, `main.py` | `openai` | Preferred provider for Tier 1/2 cascade. Values: `openai\|anthropic\|groq` |
| `EMAILDJ_QUICK_GENERATE_MODE` | `mock` | no | `api/routes/quick_generate.py`, `email_generation/preset_preview_pipeline.py` | `mock` | Values: `mock\|real`. Use `mock` for local dev and all CI jobs except nightly |

---

## LangSmith Tracing

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `LANGCHAIN_TRACING_V2` | `false` | no | LangChain framework | `false` | Set `true` to enable LangSmith trace export |
| `LANGCHAIN_API_KEY` | — | conditional | LangChain framework | `ls__fake` | Required when `LANGCHAIN_TRACING_V2=true` |
| `LANGCHAIN_PROJECT` | `emaildj-prod` | no | LangChain framework | `emaildj-dev` | Project name in LangSmith dashboard |

---

## Redis

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | yes | `infra/redis_client.py` | `redis://localhost:6379/0` | Required for session, request, and campaign caching |
| `REDIS_FORCE_INMEMORY` | `0` | no | `infra/redis_client.py`, `evals/runner.py`, `scripts/mock_e2e_smoke.py` | `1` | Set `1` to use in-memory Redis stub (CI / local testing without Redis) |

---

## Vector Store

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `VECTOR_STORE_BACKEND` | `memory` | no | `infra/vector_store.py` | `memory` | Values: `pinecone\|pgvector\|memory`. Use `memory` for local dev |
| `PINECONE_API_KEY` | — | conditional | `infra/vector_store.py` | `<redacted>` | Required when `VECTOR_STORE_BACKEND=pinecone` |
| `PINECONE_INDEX_NAME` | `emaildj-contexts` | conditional | `infra/vector_store.py` | `emaildj-test` | Required when `VECTOR_STORE_BACKEND=pinecone` |
| `PINECONE_ENVIRONMENT` | `us-east-1` | conditional | `infra/vector_store.py` | `us-east-1` | Required when `VECTOR_STORE_BACKEND=pinecone` |

---

## PostgreSQL

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./emaildj.db` | no | `infra/db.py` | `postgresql://user:password@localhost:5432/emaildj` | SQLite fallback is used in dev/test if not set |

---

## Salesforce CRM

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `SALESFORCE_CLIENT_ID` | — | conditional | CRM provider | `fake-client-id` | Required when `EMAILDJ_CRM_PROVIDER=salesforce` |
| `SALESFORCE_CLIENT_SECRET` | — | conditional | CRM provider | `<redacted>` | Required when `EMAILDJ_CRM_PROVIDER=salesforce` |
| `SALESFORCE_REDIRECT_URI` | `http://localhost:8000/auth/callback` | conditional | CRM provider | `http://localhost:8000/auth/callback` | Required when `EMAILDJ_CRM_PROVIDER=salesforce` |
| `SALESFORCE_API_VERSION` | `v59.0` | conditional | CRM provider | `v59.0` | Salesforce API version |
| `SALESFORCE_INSTANCE_URL` | — | conditional | `tests/integration/test_campaign_assignment_lifecycle.py` | `https://test.salesforce.com` | Required when `EMAILDJ_CRM_PROVIDER=salesforce` |
| `SALESFORCE_ACCESS_TOKEN` | — | conditional | `tests/integration/test_campaign_assignment_lifecycle.py` | `<redacted>` | Required when `EMAILDJ_CRM_PROVIDER=salesforce` |

---

## Campaign Intelligence

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE` | `auto` | no | `tests/integration/test_campaign_assignment_lifecycle.py` | `mock` | Values: `auto\|real\|mock\|fallback` |
| `EMAILDJ_CRM_PROVIDER` | `mock` | no | campaign agent | `mock` | Values: `salesforce\|mock` |
| `EMAILDJ_INTENT_PROVIDER` | `mock` | no | campaign agent | `mock` | Values: `bombora\|mock` |
| `BOMBORA_API_KEY` | — | conditional | `tests/integration/test_campaign_assignment_lifecycle.py` | `<redacted>` | Required when `EMAILDJ_INTENT_PROVIDER=bombora` |
| `BOMBORA_API_URL` | `https://api.bombora.com/v1/company-surge` | conditional | Bombora client | `https://api.bombora.com/v1/company-surge` | Required when `EMAILDJ_INTENT_PROVIDER=bombora` |

---

## Web Search (Deep Research)

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `SERPER_API_KEY` | — | conditional | deep research agent | `<redacted>` | Primary web search provider |
| `BRAVE_SEARCH_API_KEY` | — | conditional | deep research agent | `<redacted>` | Fallback web search provider |

---

## Alerting

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `SLACK_WEBHOOK_URL` | — | no | `infra/alerting.py` | `https://hooks.slack.com/services/fake` | Cost guard and provider failure alerts |
| `PROVIDER_FAILURE_METRICS_WEBHOOK_URL` | — | no | `infra/alerting.py` | `https://metrics.example.com/events` | Metrics sink for provider failure events |
| `ALERT_SINK_TIMEOUT_SECONDS` | `5` | no | `infra/alerting.py` | `5` | HTTP timeout for alert webhook calls |

---

## App Settings

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `CHROME_EXTENSION_ORIGIN` | — | **yes** | `main.py` (CORS), `evals/runner.py` | `chrome-extension://dev` | Required for CORS allow-list. Must match installed extension ID in prod |
| `WEB_APP_ORIGIN` | `http://localhost:5174` | yes | `main.py` (CORS) | `http://localhost:5174` | Web app origin for CORS |
| `APP_ENV` | `local` | no | `email_generation/quick_generate.py` | `local` | Values: `local\|staging\|prod` |
| `LOG_LEVEL` | `INFO` | no | `main.py` | `INFO` | Python logging level |

---

## Compliance & Generation Control

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL` | `repair` | no | `email_generation/runtime_policies.py`, `main.py` | `repair` | Values: `warn\|repair\|block`. See `docs/policy/control_contract.md` |
| `EMAILDJ_REPAIR_LOOP_ENABLED` | `1` | no | `email_generation/runtime_policies.py` | `1` | Values: `1\|0`. Disable only for controlled benchmarking |
| `EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE` | `0.01` | no | `email_generation/runtime_policies.py`, `main.py` | `0.01` | Fraction of successful outputs logged for debug (0.0–1.0) |

---

## Rate Limits & Quotas

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `EMAILDJ_WEB_BETA_KEYS` | — | yes | `api/middleware/beta_access.py` | `dev-beta-key` | Comma-separated list of valid beta access keys |
| `EMAILDJ_WEB_RATE_LIMIT_PER_MIN` | `30` | no | `api/middleware/beta_access.py` | `30` | Per-key requests per minute |
| `MONTHLY_COST_CEILING` | `100` | no | `api/middleware/cost_guard.py` | `100` | Monthly USD cost ceiling before throttling |
| `MONTHLY_COST_THROTTLE_MULTIPLIER` | `3` | no | cost guard | `3` | Cost multiplier threshold that triggers Groq-only mode |
| `BLAST_RADIUS_CONFIRM_THRESHOLD` | `200` | no | `api/routes/campaigns.py` | `200` | Campaign approval requires explicit confirmation above this recipient count |

---

## Request / Stream Settings

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `QUICK_REQUEST_TTL_SECONDS` | `300` | no | `api/routes/quick_generate.py` | `300` | TTL for in-memory quick-generate request cache |
| `QUICK_MAX_CONCURRENT_STREAMS` | `32` | no | `api/routes/quick_generate.py` | `32` | Max concurrent SSE streams via asyncio Semaphore |
| `QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD` | `5` | no | `email_generation/quick_generate.py` | `5` | Failure count before first alert fires |
| `QUICK_PROVIDER_FAILURE_ALERT_STEP` | `5` | no | `email_generation/quick_generate.py` | `5` | Subsequent alert every N failures after threshold |
| `DEEP_RESEARCH_RATE_LIMIT_PER_HOUR` | `200` | no | deep research route | `200` | Max deep research jobs per hour |
| `DEEP_RESEARCH_JOB_TTL_SECONDS` | `86400` | no | `api/routes/deep_research.py` | `86400` | TTL for deep research job results in Redis |
| `CONTEXT_VAULT_CACHE_TTL_SECONDS` | `3600` | no | context vault | `3600` | Context vault Redis TTL in seconds |

---

## Preset Preview Pipeline

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `EMAILDJ_PRESET_PREVIEW_PIPELINE` | `off` | no | `api/routes/web_mvp.py`, `main.py`, `scripts/real_mode_failfast_smoke.py` | `off` | Values: `on\|off`. Enable to expose batch preview endpoint |
| `EMAILDJ_PRESET_PREVIEW_MODEL_EXTRACTOR` | `gpt-4o-mini` | no | `email_generation/preset_preview_pipeline.py`, `main.py` | `gpt-4o-mini` | Model for research extraction step |
| `EMAILDJ_PRESET_PREVIEW_MODEL_GENERATOR` | `gpt-4o-mini` | no | `email_generation/preset_preview_pipeline.py`, `main.py` | `gpt-4o-mini` | Model for email generation step |
| `EMAILDJ_PREVIEW_INCLUDE_SUMMARY_PACK` | `0` | no | `email_generation/preset_preview_pipeline.py` | `0` | Values: `0\|1`. Include research summary pack in batch response |
| `EMAILDJ_PRESET_PREVIEW_SUMMARY_CACHE_TTL_SEC` | `900` | no | preview pipeline | `900` | Summary pack Redis cache TTL in seconds |

---

## Context Vault Enrichment

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `EMAILDJ_EXTRACTOR_ENABLE_ENRICHMENT` | `0` | no | `context_vault/extractor.py` | `0` | Values: `0\|1`. Enable account metadata enrichment |
| `EMAILDJ_EXTRACTOR_ENRICH_CONFIDENCE_MIN` | `0.75` | no | `context_vault/extractor.py` | `0.75` | Minimum extraction confidence to accept enriched field |

---

## Judge Eval (CI / Nightly Only)

These vars are used exclusively by the eval suite (`hub-api/evals/`). Not required for running
the Hub API in mock or real mode.

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `EMAILDJ_JUDGE_MODE` | `mock` | no | `evals/judge/client.py`, `evals/judge/calibrate_thresholds.py`, `evals/judge/real_corpus_runner.py` | `mock` | Values: `mock\|real`. Use `mock` in PR CI, `real` in nightly |
| `EMAILDJ_JUDGE_MODEL` | `gpt-4.1-nano` | no | `evals/judge/client.py` | `gpt-4.1-nano` | Judge model name (e.g., `gpt-4.1-mini` for nightly) |
| `EMAILDJ_JUDGE_MODEL_VERSION` | — | no | `evals/judge/client.py`, `evals/judge/pairwise_runner.py` | `gpt-4.1-nano` | Model version string used in eval reports |
| `EMAILDJ_JUDGE_SECONDARY_MODEL` | — | no | `evals/judge/client.py` | `gpt-4.1-nano` | Secondary judge for pairwise validation |
| `EMAILDJ_JUDGE_TIMEOUT_SEC` | `30` | no | `evals/judge/client.py` | `30` | Per-case judge call timeout |
| `EMAILDJ_JUDGE_CACHE_DIR` | `reports/judge/cache` | no | `evals/runner.py` | `reports/judge/cache` | Directory for judge response cache |
| `EMAILDJ_JUDGE_RUBRIC_VERSION` | — | no | `evals/judge/rubric.py` | — | Rubric version tag stamped on eval reports |
| `EMAILDJ_JUDGE_PAIRWISE_SEED` | — | no | `evals/judge/reliability.py` | `42` | Random seed for pairwise eval reproducibility |
| `EMAILDJ_JUDGE_SAMPLE_COUNT` | — | no | `evals/judge/client.py` | `1` | Number of judge samples per case (higher = more stable) |
| `EMAILDJ_JUDGE_CANDIDATE_ID` | — | no | `evals/runner.py` | `ci_candidate` | Label for the candidate run in eval reports |
| `GITHUB_SHA` | — | no | `evals/runner.py` | — | Auto-set by GitHub Actions; used to tag eval reports |

---

## Web App (Vite Frontend)

| VAR_NAME | default | required? | used by | safe test value | notes |
|---|---|---|---|---|---|
| `VITE_HUB_URL` | `http://127.0.0.1:8000` | no | `web-app/src/api/client.js` | `http://127.0.0.1:8000` | Hub API base URL for web app; set in `web-app/.env` |
| `VITE_PRESET_PREVIEW_PIPELINE` | — | no | `web-app/src/api/client.js` | `off` | Mirrors `EMAILDJ_PRESET_PREVIEW_PIPELINE` for client-side feature flag |

---

## Notes

- `required? = conditional` — only required when a specific provider/feature is enabled.
- Variables with `Observed in code = 0` in the previous version are kept for documentation;
  they may be read by indirect dependencies or are reserved for future use.
- PII: never put real API keys, access tokens, or customer data in this file.
  Use `<redacted>` as the safe test value for all secrets.
