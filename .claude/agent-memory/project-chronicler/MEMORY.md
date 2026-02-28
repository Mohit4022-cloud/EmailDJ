# Project Chronicler — Persistent Memory

## Chronicle Location

- Chronicle file: `/Users/mohit/EmailDJ/docs/CHRONICLE.md`
- Format: Single append-only file (not a directory of separate files). The user chose a single-file format rather than the default `/docs/chronicle/` multi-file structure.
- No CHRONICLE_INDEX.md is maintained for this project — the single file serves as both index and content.

## Project Identity

- Project name: EmailDJ
- Root path: `/Users/mohit/EmailDJ/`
- Sub-projects: `chrome-extension/` (Vite + MV3, vanilla JS) and `hub-api/` (FastAPI + LangGraph)
- Founding document: Entry 001 in `/Users/mohit/EmailDJ/docs/CHRONICLE.md`

## Chronicle Entry Log

| Entry | Date | Type | One-line Summary |
|---|---|---|---|
| 001 | 2026-02-28 | MILESTONE | Full project scaffolded — 65 stub files across Hub API and Chrome Extension |
| 002 | 2026-02-28 | PROGRESS | End-to-end implementation pass: contracts frozen, PII pipeline wired, SSE mock slice complete |
| 003 | 2026-02-28 | PROGRESS | Stability hardening: feature flags, explicit fallback logging, SSE retry/backoff, Redis-backed assignment state, quality-gate scripts, expanded tests |
| 004 | 2026-02-28 | PROGRESS | Quality gates green: 11 pytest passed, extension built, OpenAPI regenerated from live runtime — first full checks.sh all-green pass |

## Key Conventions for This Project

- Entry format: `## Entry NNN — YYYY-MM-DD | TYPE: Short Description`
- Entry header fields: Date, Type, Author, Previous Entry
- Append location: at the END of the file, after the last entry's closing `---`. The `*Future entries will be appended below this line.*` marker is now permanently embedded mid-file between Entry 001 and Entry 002 — it is NOT at the true bottom. Do not use it as a reference point; always append after the final `---`.
- Arrow notation: use `->` not `-->` or Unicode arrows in chronicle prose (user preference implied by Entry 001 style)
- Do NOT use `<->` — use `<->` is fine but `->` is the default for directionality

## Original Founding Vision (Entry 001 Summary)

EmailDJ is an AI SDR productivity tool: Chrome Extension (Side Panel) + Hub API (FastAPI/LangGraph). Key constraints locked at founding:
- Side Panel owns all UI state (MV3 service worker 30s termination limit)
- Pull-based assignment polling via Chrome Alarms (no persistent WS/SSE from service worker)
- 3-layer PII defense: browser regex -> Presidio NER -> opaque token vault
- VP approval hard gate in LangGraph graph before any campaign email is drafted
- 3-tier model cascade with CostGuardMiddleware auto-fallback
- Edit capture as data flywheel (every SDR edit sent back as training signal)

## Phase as of Last Entry (Entry 004, 2026-02-28)

All install-dependent quality gates unblocked and run to green. Extension `dist/` produced cleanly (icon assets added to fix Vite/crxjs build blocker). `REDIS_FORCE_INMEMORY=true` flag added to `infra/redis_client.py` and wired into `checks.sh` for CI/local gate runs. 11 pytest tests passed. `openapi.json` regenerated from live FastAPI runtime. `quick_generate.py` and `api/routes/quick_generate.py` finalized. Full `checks.sh` run: ALL GREEN. First all-green quality gate pass in project history.

## Next Session Priorities

1. Load extension in Chrome: `chrome://extensions` -> Developer mode -> Load unpacked -> `chrome-extension/dist/`
2. Provision real infra: Redis (Docker or Upstash), PostgreSQL, Pinecone index (`emaildj-context`, 1536 dims)
3. Swap mock -> real LLM: set `USE_MOCK_LLM=false`, add `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` to `.env`
4. Configure CRM OAuth: Salesforce Connected App credentials in `.env`
5. End-to-end live smoke test: Salesforce contact -> Side Panel -> QuickGenerate -> real SSE stream with real LLM output
6. Resolve Vite hub-client.js dynamic/static import warning (non-blocking)
