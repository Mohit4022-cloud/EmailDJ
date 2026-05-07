# Deployment Guide

## Service Split

- Frontend: deploy [`web-app`](/Users/mohit/EmailDJ/web-app) to Vercel as a static Vite app.
- Hub API: deploy [`hub-api`](/Users/mohit/EmailDJ/hub-api) as a separate service. Prefer Render for this repo.
- Legacy parity: [`frontend`](/Users/mohit/EmailDJ/frontend) now shares the same fail-closed `VITE_HUB_URL` behavior, but `web-app` is the documented frontend of record.

The launch-owned surface contract lives in [`docs/ops/surface_contract.md`](/Users/mohit/EmailDJ/docs/ops/surface_contract.md). `backend/` and `frontend/` are explicit legacy parity surfaces; their tests can catch migration drift, but they do not count as launch-readiness evidence.

## Why Hub API Is Not A Good Vercel Fit

- `hub-api` stores pending generate/remix stream state in process-local memory before `/web/v1/stream/{request_id}` consumes it. That pattern is implemented in [`hub-api/api/routes/web_mvp.py`](/Users/mohit/EmailDJ/hub-api/api/routes/web_mvp.py) and is unsafe on autoscaled serverless instances.
- The FastAPI app also has long-lived SSE responses plus a heavier Python dependency set (`langchain`, `presidio`, `spacy`, Redis clients, vector tooling). Render lets the app run unchanged with a persistent `uvicorn` process.

Recommended Render start command:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

## Frontend Deploy Steps

1. In Vercel, set the project root to `web-app/`.
2. Keep the default Vite build flow (`npm install`, `npm run build`, output `dist`).
3. Set frontend env vars:
   - `VITE_HUB_URL=https://<staging-or-prod-hub-api-domain>`
   - `VITE_PRESET_PREVIEW_PIPELINE=on|off`
4. Run `make launch-verify-web-app` from the repo root.
5. Redeploy after the hub-api URL is known.

If an existing Vercel project still points at `frontend/`, use the same `VITE_HUB_URL` contract there as well.

## Chrome Extension Build Steps

1. Build from `chrome-extension/`.
2. Set extension build env vars:
   - `VITE_HUB_URL=https://<staging-or-prod-hub-api-domain>`
   - `VITE_EMAILDJ_BETA_KEY=<one-beta-key-for-that-environment>`
3. Run `make launch-verify-extension` from the repo root.
4. Load or publish the generated `dist/` extension package.
5. After Chrome assigns the shipped extension ID, set `CHROME_EXTENSION_ORIGIN=chrome-extension://<extension-id>` on the hub-api and redeploy the hub-api.

The side panel also exposes runtime Settings backed by Chrome sync storage. Operators can override:

- `emaildjHubUrl`
  Runtime hub-api root URL override.
- `emaildjBetaKey`
  Runtime beta key override, sent as `X-EmailDJ-Beta-Key` when present.

## Hub API Deploy Steps

1. Create a Render web service rooted at `hub-api/`.
2. Build with `pip install -r requirements.txt`.
3. Start with `uvicorn main:app --host 0.0.0.0 --port $PORT`.
4. Attach a managed Redis instance and set `REDIS_URL`.
5. Attach a managed Postgres instance and set `DATABASE_URL`.
6. Set `VECTOR_STORE_BACKEND=pgvector` so context vectors persist in managed Postgres.
7. Set `APP_ENV=staging` first, then promote to `APP_ENV=prod` when ready.
8. Start with `EMAILDJ_LAUNCH_MODE=limited_rollout`.

## Exact Env Vars By Service

### Frontend (`web-app` on Vercel)

- `VITE_HUB_URL`
  Use the hub-api root URL. The production build now fails immediately if this is missing. Release verification requires a deployed HTTPS root URL with no path, query, or fragment.
- `VITE_PRESET_PREVIEW_PIPELINE`
  Mirror the backend preview exposure (`on` only when `EMAILDJ_PRESET_PREVIEW_PIPELINE=on` on the hub-api).

`make launch-verify-web-app` accepts `EMAILDJ_EXPECTED_HUB_URL` and `EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE` as explicit release verification inputs. If those are unset, it falls back to `VITE_HUB_URL` and `VITE_PRESET_PREVIEW_PIPELINE`.

### Chrome Extension (`chrome-extension`)

- `VITE_HUB_URL`
  Use the hub-api root URL baked into the extension build. The build uses this value to emit a narrow `host_permissions` entry such as `https://hub-staging.example.com/*`. Operators can override the URL later in the side panel Settings tab, but a launch package must still be built and verified against the intended Hub API origin. In production-like runtime, the extension refuses the localhost fallback and requires a deployed HTTPS hub-api root URL with no path, query, or fragment unless a saved operator override is present.
- `VITE_EMAILDJ_BETA_KEY`
  Required for release verification. Operators can override it later in the side panel Settings tab. Production-like runtime rejects missing values and `dev-beta-key`; use a non-dev key.

`make launch-verify-extension` accepts `EMAILDJ_EXPECTED_HUB_URL` and `EMAILDJ_EXPECTED_BETA_KEY` as explicit release verification inputs. If those are unset, it falls back to `VITE_HUB_URL` and `VITE_EMAILDJ_BETA_KEY`.

### Hub API (Render)

- `APP_ENV`
  `staging` or `prod`.
- `USE_PROVIDER_STUB`
  `0` for deployed services.
- `EMAILDJ_REAL_PROVIDER`
  `openai`, `anthropic`, or `groq`.
- `OPENAI_API_KEY`
  Required when `EMAILDJ_REAL_PROVIDER=openai`. Also required whenever `EMAILDJ_PRESET_PREVIEW_PIPELINE=on`.
- `ANTHROPIC_API_KEY`
  Required when `EMAILDJ_REAL_PROVIDER=anthropic`.
- `GROQ_API_KEY`
  Required when `EMAILDJ_REAL_PROVIDER=groq`.
- `REDIS_URL`
  Required for deployed services. Must not point to localhost in launch modes.
- `REDIS_FORCE_INMEMORY`
  Must be unset or `0` for deployed services.
- `DATABASE_URL`
  Required for deployed services. Must use a non-local managed Postgres host in launch modes.
- `VECTOR_STORE_BACKEND`
  Required value for launch modes: `pgvector`.
- `WEB_APP_ORIGIN`
  The deployed Vercel frontend origin, for example `https://app.example.com`.
- `CHROME_EXTENSION_ORIGIN`
  The shipped extension origin, for example `chrome-extension://<extension-id>`.
- `EMAILDJ_WEB_BETA_KEYS`
  Comma-separated secret beta keys. Do not include `dev-beta-key` in staging or prod.
- `EMAILDJ_WEB_RATE_LIMIT_PER_MIN`
  Explicit pinned limit, for example `300`.
- `EMAILDJ_LAUNCH_MODE`
  Start with `limited_rollout`.
- `EMAILDJ_PRESET_PREVIEW_PIPELINE`
  `off` by default. Turn `on` only when you intentionally expose preview routes and have `OPENAI_API_KEY` set.

## Local-Only Vs Deployed-Service Vars

- Local-only defaults:
  - `VITE_HUB_URL=http://127.0.0.1:8000`
  - `VITE_EMAILDJ_BETA_KEY=dev-beta-key`
  - `WEB_APP_ORIGIN=http://localhost:5174`
  - `EMAILDJ_WEB_BETA_KEYS=dev-beta-key`
  - `REDIS_FORCE_INMEMORY=1`
  - `DATABASE_URL=sqlite+aiosqlite:///./emaildj.db`
  - `VECTOR_STORE_BACKEND=memory`
- Deployed-service vars:
  - `APP_ENV`
  - `REDIS_URL`
  - `DATABASE_URL`
  - `VECTOR_STORE_BACKEND=pgvector`
  - `WEB_APP_ORIGIN`
  - `CHROME_EXTENSION_ORIGIN`
  - `EMAILDJ_WEB_BETA_KEYS`
  - `EMAILDJ_WEB_RATE_LIMIT_PER_MIN`
  - `USE_PROVIDER_STUB=0`
  - provider API keys

## Launch Verification Contract

- `STAGING_BASE_URL`
  The staging hub-api root URL, not the Vercel frontend URL. Must be an HTTPS root URL with no path, query, or localhost host.
- `PROD_BASE_URL`
  The production hub-api root URL, not the Vercel frontend URL. Must be an HTTPS root URL with no path, query, or localhost host, and must differ from `STAGING_BASE_URL`.
- `BETA_KEY`
  One exact non-dev key value from the deployed `EMAILDJ_WEB_BETA_KEYS` list.

Example mapping:

```text
hub-api staging EMAILDJ_WEB_BETA_KEYS=staging-key-a,staging-key-b
operator BETA_KEY=staging-key-a
operator STAGING_BASE_URL=https://hub-staging.example.com
frontend VITE_HUB_URL=https://hub-staging.example.com
```

After those operator-machine values are exported, run the deployed launch gate from the repo root:

```bash
make launch-preflight
make launch-verify-deployed
```

`make launch-preflight` is the fast operator-input check for `STAGING_BASE_URL`, `PROD_BASE_URL`, `BETA_KEY`, and provider transport. `make launch-verify-deployed` runs the same preflight again, then verifies the web-app and Chrome-extension release bundles against the staging Hub URL and beta key, captures staging and production runtime snapshots, runs a small real-provider smoke, runs staging Hub API HTTP smoke for `generate,remix`, merges those summaries, and then runs `launch_check.py` as a failing gate. Launch-check now requires the canonical HTTP smoke artifact to prove `external_provider` traffic plus green `generate` and `remix` route coverage in launch modes. Use `EMAILDJ_DEPLOYED_SMOKE_FLOWS=generate,remix,preview` only when the staging preview route is intentionally enabled.

## Manual Values You Still Need To Create

- Real provider API keys.
- Non-dev beta key values for staging and prod.
- Final Vercel frontend origin(s).
- Final extension origin(s).
- Managed Redis connection string.
