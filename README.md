# EmailDJ MVP 0.5 (`emaildj-mvp-0.5`)

New standalone repo for EmailDJ Remix Studio MVP launch.

This repo preserves the existing Remix Studio UI flow and adds:
- generate once -> stable blueprint -> real-time remix
- target/prospect/sender AI enrichment buttons
- tool-only retrieval + citations + caching
- SSE progress streaming
- deterministic validators + repair loop
- prompt hash/version + trace metadata

## Repo layout
- `web-app/` primary Vite + vanilla JS Remix Studio web UI
- `hub-api/` primary FastAPI Hub API + SSE + generation, validation, launch checks, and eval harness
- `chrome-extension/` MV3 extension client surface
- `frontend/` legacy parity UI, kept only for explicit legacy checks
- `backend/` legacy backend, kept only for explicit legacy checks
- `shared/` contract notes
- `docs/` port list + acceptance checklist

## Local setup

### 1) Hub API
```bash
cd hub-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2) Web App
```bash
cd web-app
npm install
```

### 3) Chrome Extension
```bash
cd chrome-extension
npm install
```

## Run (one command)
From repo root:
```bash
make dev
```
This starts:
- Hub API: `http://127.0.0.1:8000`
- Web App: `http://127.0.0.1:5174`

Local dev now defaults to real AI (`USE_PROVIDER_STUB=0`) and requires `OPENAI_API_KEY`.
`make dev` loads provider secrets from `hub-api/.env`, then forces a local web contract
(`APP_ENV=local`, localhost origins, in-memory Redis, and `dev-beta-key`) so staging/prod
values in `.env` do not accidentally poison a local run.

## Tests
From repo root:
```bash
make test
```

Or individually:
```bash
make hub-api-test
make web-app-test
make chrome-extension-test
```

## Build
```bash
make build
```

Legacy surfaces remain available only through explicit targets:

```bash
make legacy-backend-test
make legacy-frontend-test
make legacy-build
```

## API overview
- `POST /web/v1/generate`
- `POST /web/v1/remix`
- `POST /web/v1/preset-preview`
- `POST /web/v1/preset-previews/batch`
- `POST /web/v1/enrich/target`
- `POST /web/v1/enrich/prospect`
- `POST /web/v1/enrich/sender`
- `GET /web/v1/stream/{request_id}`
- `GET /web/v1/debug/config`
- `POST /research/`
- `GET /research/{job_id}/status`

### Company context migration note
- `company_context.seller_offerings` is seller-facing offering context used by generation.
- `company_context.internal_modules` is never passed to generation/planning and is only for internal UI mapping.
- `company_context.other_products` remains backward-compatible as a migration field.

### Debug prompt tracing
- Set `DEBUG_PROMPT=1` to log normalized context, selected beats, assembled prompt messages, and copy provenance map in backend logs.
- Prompt tracing is disabled by default and is not returned to normal users.

## Non-negotiable guardrails implemented
- model cannot browse directly; retrieval through tools only
- citations on enrichment outputs (`url`, `retrieved_at`, `published_at|Unknown`)
- manual overrides win over AI fields
- slider/remix paths use blueprint, not raw deep research
- deterministic validation for CTA drift/repetition/truncation/leakage/length
