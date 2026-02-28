# EmailDJ — Project Chronicle

This is an append-only project history. Each entry records a session, milestone, decision, or pivot.
New entries are added BELOW existing ones. Existing entries are never edited or removed.

---

## Entry 001 — 2026-02-28 | MILESTONE: Full Project Scaffolding

**Date:** 2026-02-28
**Type:** MILESTONE
**Author:** AI-assisted (Claude Sonnet 4.6 — architect model)
**Previous Entry:** None — this is the founding document.

---

### What Is EmailDJ

EmailDJ is an AI-powered SDR (Sales Development Representative) productivity tool. It sits inside Gmail or a CRM (initially Salesforce/HubSpot) via a Chrome Extension Side Panel and helps SDRs generate, personalize, and manage outbound email sequences — while giving VP-level managers approval gates over campaign blasts.

The architecture is hub-and-spoke:

- **Chrome Extension (MV3)** — the CRM intelligence layer. It parses the CRM DOM, extracts prospect context, presents a Side Panel UI for email generation, and captures SDR edits as training signal.
- **Hub API (FastAPI + LangGraph)** — the orchestration and generation engine. It runs NLP pipelines, manages a Context Vault (Redis + Postgres + Pinecone), calls LLMs via a 3-tier model cascade, enforces PII protection, and exposes a pull-based assignment queue for delegation.

**Project root:** `/Users/mohit/EmailDJ/`
**Sub-projects:** `chrome-extension/` and `hub-api/`
**Stack:**
- Chrome Extension: Vite + `@crxjs/vite-plugin`, vanilla JS (no framework), MV3
- Hub API: FastAPI, LangGraph, LangChain, Redis, Pinecone/pgvector, Presidio PII, SQLAlchemy async, PostgreSQL

---

### What Was Accomplished in This Session

The architect model (Claude Sonnet 4.6) designed and scaffolded the entire project in a single session. The deliberate strategy was:

1. Use an expensive, capable model to write detailed `IMPLEMENTATION INSTRUCTIONS` comments inside every stub file — capturing all architectural intent in the code itself.
2. Use a cheaper model in a follow-up session to read those comments and fill in the actual implementations, without needing to re-read any architecture docs.

**Total files scaffolded: 65** across both sub-projects. All files are stubs with implementation-ready comments. None contain production logic yet.

---

#### Chrome Extension — Files Scaffolded

| File | Role |
|---|---|
| `manifest.json` | MV3 compliant. Permissions: `activeTab`, `storage`, `sidePanel`, `alarms`. |
| `package.json` | Dependencies: `@crxjs/vite-plugin`, `vite`. |
| `vite.config.js` | Build system config for MV3 Chrome extension output. |
| `src/background/background.js` | Service worker. Navigation detection, alarm-based polling, message routing. |
| `src/content/content.js` | Content script. DOM payload extraction, message passing to background. |
| `src/content/navigation-detector.js` | Tier 1 DOM parser. Detects CRM page navigation via URL change. |
| `src/content/mutation-observer.js` | Tier 2 DOM parser. Watches DOM mutations for SPA re-renders. |
| `src/content/polling-fallback.js` | Tier 3 DOM parser. Interval polling as final fallback. |
| `src/content/pii-prefilter.js` | Layer 1 PII defense. Regex-based prefilter before any data leaves the browser. |
| `src/sidepanel/sidepanel.js` | Stateful Side Panel process. Owns all UI state (service workers terminate after 30s). |
| `src/sidepanel/hub-client.js` | Hub API client. SSE streaming handler, assignment polling, edit capture. |
| `src/sidepanel/components/QuickGenerate.js` | UI: one-click email generation trigger. |
| `src/sidepanel/components/EmailEditor.js` | UI: editable email draft with diff/edit capture. |
| `src/sidepanel/components/AssignedCampaigns.js` | UI: shows assignments pulled from delegation queue. |
| `src/sidepanel/components/ContextSummary.js` | UI: summarized prospect context from Context Vault. |
| `src/sidepanel/components/PersonalizationSlider.js` | UI: controls personalization depth/tone. |

**3-Tier DOM Parsing system:** `navigation-detector.js` (primary) → `mutation-observer.js` (SPA fallback) → `polling-fallback.js` (final fallback). Each tier hands off to the next only on failure.

---

#### Hub API — Files Scaffolded

**Entry point and middleware:**
| File | Role |
|---|---|
| `main.py` | FastAPI app factory. Lifespan handler for startup/shutdown of Redis, Pinecone, DB. |
| `middleware/pii_redaction.py` | `PiiRedactionMiddleware` — Presidio NER at ingress. Layer 2 PII defense. |
| `middleware/cost_guard.py` | `CostGuardMiddleware` — tracks daily LLM spend; enforces Tier 3 fallback when threshold hit. |

**API routes (all stubs):**
| Route Module | Endpoints |
|---|---|
| `routes/generate.py` | `POST /generate/quick`, `GET /generate/stream/{id}` |
| `routes/research.py` | `POST /research/prospect`, `GET /research/status/{id}` |
| `routes/campaigns.py` | `POST /campaigns/`, `GET /campaigns/{id}`, `POST /campaigns/{id}/approve` |
| `routes/assignments.py` | `GET /assignments/poll`, `POST /assignments/{id}/accept` |
| `routes/vault.py` | `POST /vault/ingest`, `GET /vault/context/{prospect_id}` |
| `routes/webhooks.py` | `POST /webhooks/salesforce`, `POST /webhooks/hubspot` |

**LangGraph — VP Campaign Builder (`agents/campaign_builder/`):**

5-node graph with a human interrupt gate:

```
intent_classifier
      |
crm_query_agent
      |
intent_data_agent
      |
[HUMAN INTERRUPT — VP approval required]
      |
audience_builder
      |
sequence_drafter
```

No email sequence is drafted without explicit VP approval. This is the "blast radius" protection gate.

**Context Vault (`services/context_vault/`):**
| File | Role |
|---|---|
| `models.py` | Pydantic models for vault entries. |
| `extractor.py` | 4-stage NLP pipeline: entity extraction → intent inference → relationship mapping → temporal tagging. |
| `merger.py` | Conflict resolution: newer signal wins by default; field-level merge with provenance tracking. |
| `embedder.py` | Embeds context chunks for semantic retrieval (Pinecone / pgvector). |
| `cache.py` | Redis cache layer. TTL: 1 hour. Warm on every CRM navigation event. |

**Email generation (`services/email_generator/`):**
| File | Role |
|---|---|
| `model_cascade.py` | 3-tier LLM fallback. Tier 1: GPT-4o / Claude Opus 4.6. Tier 2: GPT-4o-mini / Claude Haiku 4.5. Tier 3: Groq Llama 3.3. |
| `quick_generate.py` | Low-latency generation entry point. Reads from pre-warmed Redis cache. |
| `streaming.py` | SSE streaming to the Side Panel. |
| `multi_thread.py` | Persona coherence enforcement for multi-threaded campaigns. |
| `prompt_templates.py` | Prompt library for all generation modes. |

**PII pipeline (`services/pii_pipeline/`):**
| File | Role |
|---|---|
| `presidio_redactor.py` | Layer 2: Presidio NER. Catches contextual PII missed by regex. |
| `token_vault.py` | Layer 3: Opaque tokenization. Replaces PII with tokens before any LLM call; resolves tokens on output. |

**Delegation engine:** `services/assignment_queue.py` — pull-based SDR assignment queue exposed via `/assignments/poll`.

**Infra (`core/`):**
| File | Role |
|---|---|
| `redis_client.py` | Singleton Redis client. |
| `database.py` | SQLAlchemy async engine + session factory. |
| `vector_store.py` | Pinecone / pgvector abstraction layer. |

**CRM integrations:** `integrations/salesforce.py`, `integrations/hubspot.py` — OAuth stubs.

---

### Key Architectural Decisions Recorded

1. **Side Panel owns state.** MV3 service workers terminate after 30 seconds of inactivity. The Side Panel is a persistent process and is the single source of truth for all UI state. `sidepanel.js` never delegates state to `background.js`.

2. **Pull-based assignment polling.** MV3 prevents persistent WebSocket or SSE connections from service workers. The extension uses Chrome Alarms API to poll `/assignments/poll` on a configurable interval instead.

3. **3-layer PII defense — no raw PII ever reaches any LLM API.**
   - Layer 1: `pii-prefilter.js` — regex prefilter in the browser, before the HTTP request is made.
   - Layer 2: `PiiRedactionMiddleware` — Presidio NER at Hub API ingress, catches contextual PII.
   - Layer 3: `token_vault.py` — replaces all remaining PII with opaque tokens before any LLM call; vault resolves tokens on the way back out.

4. **Pre-staging cache warm for low latency.** The extension sends a DOM payload on every CRM navigation event. The Hub pre-warms the Redis cache immediately. Target P95 latency on QuickGenerate: ~2 seconds.

5. **Edit capture as data flywheel.** Every SDR edit to a generated email is captured by `hub-client.js` and sent back to the Hub. This is the primary training signal for prompt evolution over time.

6. **VP approval hard gate.** The LangGraph campaign builder graph includes a human interrupt node between `intent_data_agent` and `audience_builder`. No email sequence reaches `sequence_drafter` without explicit VP approval. This is the "blast radius" protection for outbound campaigns.

7. **3-tier model cascade with cost guard.**
   - Tier 1 (GPT-4o / Claude Opus 4.6): intent classification, CRM synthesis, campaign planning.
   - Tier 2 (GPT-4o-mini / Claude Haiku 4.5): individual email drafting.
   - Tier 3 (Groq Llama 3.3): cheap classification tasks and cost-throttle fallback.
   - `CostGuardMiddleware` enforces automatic Tier 3 fallback when daily spend thresholds are exceeded.

8. **Cross-thread narrative coherence.** `multi_thread.py` enforces a strict rule: no email in a multi-threaded campaign may contain information that could only be known if the sender had spoken to another person at the target company. Each persona email must read as if written in isolation.

---

### Current Status (as of 2026-02-28)

**Phase:** Scaffolded. All 65 stubs written. No production logic implemented yet.

**What exists:** Directory structure, file stubs, and detailed `IMPLEMENTATION INSTRUCTIONS` comments in every file.

**What does not exist yet:** Working Chrome extension build, running Hub API, tests, infra provisioned, env vars configured.

---

### Recommended Next Session — Implementation Workflow

A capable model reading the stub files' `IMPLEMENTATION INSTRUCTIONS` comments should be able to implement each file without re-reading architecture docs.

Recommended sequence:

1. **Fill in Hub API core stubs first** — `core/redis_client.py`, `core/database.py`, `core/vector_store.py`. These are dependencies for everything else.
2. **Implement Context Vault** — `services/context_vault/` in order: `models.py` → `extractor.py` → `merger.py` → `embedder.py` → `cache.py`.
3. **Implement PII pipeline** — `services/pii_pipeline/presidio_redactor.py`, then `token_vault.py`.
4. **Implement email generation** — `model_cascade.py` → `quick_generate.py` → `streaming.py` → `multi_thread.py`.
5. **Implement API routes** — `/generate` and `/vault` first (needed for E2E smoke test); others after.
6. **Implement LangGraph campaign builder** — 5 nodes + human interrupt gate.
7. **Implement Chrome Extension** — `background.js`, `content.js`, then Side Panel components.
8. **Verify extension build:** `cd /Users/mohit/EmailDJ/chrome-extension && npm install && npm run build`
9. **Verify Hub API starts:** `cd /Users/mohit/EmailDJ/hub-api && uvicorn main:app --reload`
10. **Configure env vars:** Copy `hub-api/.env.example` to `hub-api/.env`. Add: Salesforce OAuth credentials, Redis URL, Pinecone API key, PostgreSQL DSN, LLM API keys.
11. **Provision infra:** Redis (local Docker or Upstash), Pinecone index (`emaildj-context`, 1536 dims), PostgreSQL.
12. **End-to-end smoke test:** Navigate to a Salesforce contact page → verify Side Panel populates → click QuickGenerate → verify SSE stream delivers email draft.

---

### Open Questions / Risks at Scaffolding Complete

- Presidio NER language model must be downloaded at Hub startup; latency impact on cold start needs measurement.
- Pinecone vs pgvector choice not yet finalized — `vector_store.py` abstracts both but the Pinecone index dimension (1536) assumes OpenAI `text-embedding-3-small`. If switched to a different embedding model, dimension must change.
- Chrome Extension CRM DOM selectors for Salesforce Lightning and HubSpot are not yet written — these are the most fragile part of the system and likely to break on CRM UI updates.
- Token vault persistence strategy not fully specified: in-memory dict (fine for single process) vs Redis-backed (required for multi-worker Hub deployment).

---

*Future entries will be appended below this line.*

---
