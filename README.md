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

The machine-readable launch surface manifest lives at [`docs/ops/launch_surfaces.json`](/Users/mohit/EmailDJ/docs/ops/launch_surfaces.json). `make surface-contract` validates that manifest, the Makefile gates, CI, and operator docs agree on the same launch-owned surfaces.

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
cp .env.example .env
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

Local launch gates:

```bash
make launch-gates-local
```

This runs the surface contract gate, the three launch-owned surface test suites, mock lock-compliance smoke, preview/generate parity, adversarial mock eval, full mock eval, and `make launch-check`. The full mock eval runs after the adversarial subset so the canonical provider-stub report ends on the broad 96-case artifact.
It also runs `make render-blueprint-check` so the Render Hub API handoff cannot drift from the managed Redis/Postgres and Dashboard-filled secret contract.

Deployed launch gate, after `STAGING_BASE_URL`, `PROD_BASE_URL`, and explicit `BETA_KEY` are exported on the operator machine:

```bash
make launch-verify-deployed
```

This runs launch preflight, captures staging and production runtime snapshots, runs a small real-provider smoke, runs staging Hub API HTTP smoke for `generate,remix`, then runs the launch check as a failing gate. Set `EMAILDJ_DEPLOYED_SMOKE_FLOWS=generate,remix,preview` only when the staging preview route is intentionally enabled.

Web app release gate, after `VITE_HUB_URL` or `EMAILDJ_EXPECTED_HUB_URL` points at the deployed Hub API and `VITE_PRESET_PREVIEW_PIPELINE` is explicitly set:

```bash
make launch-verify-web-app
```

This runs web app tests, syntax checks, build, and release config verification against the built `dist/` package.

Extension release gate, after `VITE_HUB_URL` or `EMAILDJ_EXPECTED_HUB_URL` points at the deployed Hub API:

```bash
make launch-verify-extension
```

This runs extension tests, syntax checks, build, and release config verification against the built `dist/` package.

## Build
```bash
make build
```

## Launch Readiness

Refresh the launch report from existing artifacts without treating known launch blockers as a command failure:

```bash
make launch-check
```

`make launch-check` includes the canonical localhost smoke artifact at `hub-api/debug_runs/smoke/manual/summary.json` when computing freshness and provenance. If that artifact is missing or stale, the report stays honest and lists the guarded smoke as an operator next step.

Check the deployed-run operator inputs before running the full deployed gate:

```bash
make launch-preflight
```

This is intentionally strict. It exits nonzero until `STAGING_BASE_URL`, `PROD_BASE_URL`, and a non-dev `BETA_KEY` are exported on the operator machine.

Run a guarded localhost smoke against an already-running Hub API:

```bash
EMAILDJ_CONFIRM_LOCALHOST_SMOKE=1 make localhost-smoke
```

This smoke can call the provider configured on the running Hub API. Defaults are `http://127.0.0.1:8000`, `dev-beta-key`, `mode=smoke`, and `flows=generate,remix`. The command writes per-flow summaries under `hub-api/debug_runs/smoke/manual/`, merges them into `hub-api/debug_runs/smoke/manual/summary.json`, then refreshes `hub-api/reports/launch/latest.json` and `hub-api/reports/launch/latest.md`.

Launch modes are fail-closed at Hub API startup. `limited_rollout` and `broad_launch` require pinned `WEB_APP_ORIGIN`, pinned `CHROME_EXTENSION_ORIGIN`, non-dev `EMAILDJ_WEB_BETA_KEYS`, explicit `EMAILDJ_WEB_RATE_LIMIT_PER_MIN`, real provider mode, managed `REDIS_URL`, managed `DATABASE_URL`, and `VECTOR_STORE_BACKEND=pgvector`.

The repo-root [`render.yaml`](/Users/mohit/EmailDJ/render.yaml) is the deployment handoff for the Hub API. It provisions the Render web service plus managed Postgres and Redis, keeps provider-stub mode off, and leaves environment-specific launch inputs as Dashboard-filled values. See [docs/ops/deployment.md](/Users/mohit/EmailDJ/docs/ops/deployment.md) before creating or updating the Blueprint.

Check that handoff without Render CLI access:

```bash
make render-blueprint-check
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
- deterministic validation fallback is dev-only; launch modes fail closed on validation failure
