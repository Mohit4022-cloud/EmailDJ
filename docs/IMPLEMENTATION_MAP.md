# EmailDJ Naming/Path Alignment

This document maps architecture-language names in `docs/CHRONICLE.md` to current repository paths.

## Hub API path map
- `core/redis_client.py` -> `/Users/mohit/EmailDJ/hub-api/infra/redis_client.py`
- `core/database.py` -> `/Users/mohit/EmailDJ/hub-api/infra/db.py`
- `core/vector_store.py` -> `/Users/mohit/EmailDJ/hub-api/infra/vector_store.py`
- `services/context_vault/*` -> `/Users/mohit/EmailDJ/hub-api/context_vault/*`
- `services/email_generator/*` -> `/Users/mohit/EmailDJ/hub-api/email_generation/*`
- `services/pii_pipeline/*` -> `/Users/mohit/EmailDJ/hub-api/pii/*`
- `services/assignment_queue.py` -> `/Users/mohit/EmailDJ/hub-api/delegation/engine.py`

## Extension path map
- `src/background/background.js` -> `/Users/mohit/EmailDJ/chrome-extension/src/background/service-worker.js`
- `src/content/*` -> `/Users/mohit/EmailDJ/chrome-extension/src/content-scripts/*`
- `src/sidepanel/*` -> `/Users/mohit/EmailDJ/chrome-extension/src/side-panel/*`

## Contract freeze artifacts
- API schemas: `/Users/mohit/EmailDJ/hub-api/api/schemas.py`
- OpenAPI artifact: `/Users/mohit/EmailDJ/hub-api/openapi.json`
- OpenAPI generator: `/Users/mohit/EmailDJ/hub-api/scripts/generate_openapi.py`
- Runtime message types: `CONTENT_READY`, `PAYLOAD_READY`, `SYNC_TICK`, `PING`
- SSE event types: `start`, `token`, `done`, `error`

## Runtime feature flags
- `EMAILDJ_QUICK_GENERATE_MODE=mock|real` (default `mock`)
- `EMAILDJ_REAL_PROVIDER=openai|anthropic|groq`

## Quality gates
- Script: `/Users/mohit/EmailDJ/hub-api/scripts/checks.sh`
- Smoke script: `/Users/mohit/EmailDJ/hub-api/scripts/mock_e2e_smoke.py`
