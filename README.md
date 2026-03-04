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
- `frontend/` Vite + vanilla JS UI
- `backend/` FastAPI + SSE + compile/render + enrichment services
- `shared/` contract notes
- `docs/` port list + acceptance checklist

## Local setup

### 1) Backend
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2) Frontend
```bash
cd frontend
npm install
```

## Run (one command)
From repo root:
```bash
make dev
```
This starts:
- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5174`

Default local mode uses `USE_PROVIDER_STUB=1` unless you override env values.

## Tests
From repo root:
```bash
make test
```

Or individually:
```bash
cd backend && source .venv/bin/activate && pytest -q
cd frontend && npm test && npm run check:syntax
```

## Build
```bash
cd frontend && npm run build
```

## API overview
- `POST /web/v1/generate`
- `POST /web/v1/remix`
- `POST /web/v1/preset-preview`
- `POST /web/v1/enrich/target`
- `POST /web/v1/enrich/prospect`
- `POST /web/v1/enrich/sender`
- `GET /web/v1/stream/{request_id}`
- `GET /web/v1/debug/config`

## Non-negotiable guardrails implemented
- model cannot browse directly; retrieval through tools only
- citations on enrichment outputs (`url`, `retrieved_at`, `published_at|Unknown`)
- manual overrides win over AI fields
- slider/remix paths use blueprint, not raw deep research
- deterministic validation for CTA drift/repetition/truncation/leakage/length
