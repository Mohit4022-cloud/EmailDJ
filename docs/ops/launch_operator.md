# Launch Operator Guide

Run from [`hub-api`](/Users/mohit/EmailDJ/hub-api).

Deployment contract and env handoff live in [`docs/ops/deployment.md`](/Users/mohit/EmailDJ/docs/ops/deployment.md).
Launch-owned versus legacy surface boundaries live in [`docs/ops/surface_contract.md`](/Users/mohit/EmailDJ/docs/ops/surface_contract.md).

## Required env vars

- Common:
  - `CHROME_EXTENSION_ORIGIN`
  - `EMAILDJ_WEB_BETA_KEYS`
  - `REDIS_FORCE_INMEMORY=1` for local verification
  - `REDIS_URL`, `DATABASE_URL`, and `VECTOR_STORE_BACKEND=pgvector` for launch-mode services
- Launch mode:
  - `EMAILDJ_LAUNCH_MODE=dev|limited_rollout|broad_launch`
- Real provider:
  - `EMAILDJ_REAL_PROVIDER=openai|anthropic|groq`
  - `OPENAI_API_KEY` when provider is `openai`
  - `ANTHROPIC_API_KEY` when provider is `anthropic`
  - `GROQ_API_KEY` when provider is `groq`
- Optional route overrides:
  - `EMAILDJ_ROUTE_GENERATE_ENABLED=0|1`
  - `EMAILDJ_ROUTE_REMIX_ENABLED=0|1`
  - `EMAILDJ_ROUTE_PREVIEW_ENABLED=0|1`

## Operator machine env

- `STAGING_BASE_URL`
  Must point to the staging hub-api root URL, not the frontend URL. Must be an HTTPS root URL with no path, query, or localhost host.
- `PROD_BASE_URL`
  Must point to the production hub-api root URL, not the frontend URL. Must be an HTTPS root URL with no path, query, or localhost host, and must differ from `STAGING_BASE_URL`.
- `BETA_KEY`
  Must exactly match one non-dev deployed value from `EMAILDJ_WEB_BETA_KEYS`.

## Backend tests

## Surface contract

Run this from the repo root before interpreting launch evidence:

```bash
cd /Users/mohit/EmailDJ
make surface-contract
```

This fails if primary launch gates or CI drift back toward the legacy `backend/` or `frontend/` surfaces.

## Backend tests

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
pytest -q tests
```

## Shim verification

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
python scripts/capture_ui_session.py --provider-path provider_shim --out debug_runs/launch_ops/provider_shim/manual
```

Expected summary artifact:
- `debug_runs/launch_ops/provider_shim/manual/summary.json`
- `provider_source` must be `provider_shim`

## External-provider targeted replay

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
python scripts/capture_ui_session.py --provider-path external_provider --out debug_runs/launch_ops/external_provider/manual
```

Expected summary artifact:
- `debug_runs/launch_ops/external_provider/manual/summary.json`
- `provider_source` must be `external_provider`

The capture tool reads the first configured `EMAILDJ_WEB_BETA_KEYS` value for `X-EmailDJ-Beta-Key`. It defaults `EMAILDJ_LAUNCH_MODE=dev` for local capture unless explicitly overridden, so preview can be exercised even when `.env` has `APP_ENV=staging`. If credentials or beta access are wrong, the command fails closed with the endpoint and HTTP status.

## External-provider full harness

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
./scripts/eval:full --real
```

Artifacts:
- `reports/external_provider/latest.json`
- `reports/external_provider/latest.md`
- `reports/external_provider/history/`

Mock and shim-backed harness artifacts stay separate:
- `reports/provider_stub/latest.json`
- `reports/provider_stub/latest.md`

## Localhost smoke summary

Start the server first:

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
uvicorn main:app --reload
```

Then run the live smoke path:

```bash
cd /Users/mohit/EmailDJ
EMAILDJ_CONFIRM_LOCALHOST_SMOKE=1 make localhost-smoke
```

Expected summary artifact:
- `debug_runs/smoke/manual/summary.json`

The smoke runner now fails clearly if the localhost server is not healthy. By default the root command runs `generate,remix`, writes per-flow summaries under `debug_runs/smoke/manual/`, and merges them into the canonical summary. The root command is confirmation-gated because it can call whichever provider is configured on the running Hub API.

## Launch-check command

Fastest deployed verification path, once `STAGING_BASE_URL`, `PROD_BASE_URL`, and explicit `BETA_KEY` are exported on the operator machine:

```bash
cd /Users/mohit/EmailDJ
make launch-verify-deployed
```

This runs preflight, verifies the web-app and Chrome-extension release bundles against the staging Hub URL and beta key, captures staging and production runtime snapshots, runs a small real-provider smoke, runs staging Hub API HTTP smoke for `generate,remix`, merges those summaries, and then runs launch check as a failing gate. Add `EMAILDJ_DEPLOYED_SMOKE_FLOWS=generate,remix,preview` only when the staging preview route is intentionally enabled.

Release verification defaults:

- `EMAILDJ_EXPECTED_HUB_URL=${STAGING_BASE_URL}`
- `EMAILDJ_EXPECTED_BETA_KEY=${BETA_KEY}`
- `EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE=off`

Override those only when the bundle is intentionally built for a different verified target.

Launch-check treats the merged HTTP smoke summary as route coverage evidence. In `limited_rollout` and `broad_launch`, the canonical smoke artifact must prove:

- `provider_source_counts.external_provider > 0`
- green `generate` route coverage
- green `remix` route coverage
- green `preview` route coverage only when the deployed runtime snapshot has preview enabled

Fresh run:

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
python scripts/launch_check.py
```

Artifact-only read:

```bash
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
python scripts/launch_check.py --from-artifacts --allow-not-ready
```

`launch_check.py` now loads `hub-api/.env` before resolving runtime policies, so artifact-only runs reflect the repo's configured `APP_ENV` and default `launch_mode` unless explicit shell env overrides them.

The artifact-only read includes the canonical localhost smoke summary by default:

```bash
debug_runs/smoke/manual/summary.json
```

Use `--localhost-smoke-summary <path>` only when reviewing a nonstandard smoke artifact.

Canonical launch artifacts:
- `reports/launch/latest.json`
- `reports/launch/latest.md`

## How to interpret artifacts

- `provider_source=provider_stub`: stub harness only
- `provider_source=provider_shim`: real route path with local fake provider
- `provider_source=external_provider`: actual provider-backed verification exists
- `provider_green=green` only counts when an external-provider artifact exists
- `provider_green=not_run` means no external-provider artifact was produced
- `http_smoke_route_missing:<route>` means the deployed HTTP smoke artifact did not prove that route
- `http_smoke_external_provider_missing_for_launch_mode:<mode>` means the smoke artifact was not provider-backed and cannot satisfy launch evidence

## Launch categories

`Stable for MVP launch behind limited rollout` requires:
- `EMAILDJ_LAUNCH_MODE=limited_rollout`
- `backend_green=green`
- `harness_green=green`
- `shim_green=green`
- `remix_green=green`
- pinned `WEB_APP_ORIGIN` and `CHROME_EXTENSION_ORIGIN`
- non-dev `EMAILDJ_WEB_BETA_KEYS`
- managed Redis, managed Postgres, and `VECTOR_STORE_BACKEND=pgvector`
- deployed HTTP smoke for `generate` and `remix` with `external_provider` evidence
- `required_field_miss_count=0`
- `under_length_miss_count=0`
- `provider_green` may be `green` or `not_run`

In `limited_rollout`, preview is disabled by default unless `EMAILDJ_ROUTE_PREVIEW_ENABLED=1` is set explicitly. A preview `route_disabled` artifact is expected in that mode and is not a launch blocker.

Deterministic validation fallback is only allowed in `EMAILDJ_LAUNCH_MODE=dev`. `limited_rollout` and `broad_launch` fail closed on CTCO validation failures instead of emitting deterministic fallback drafts.

`Stable for broad launch` requires:
- `EMAILDJ_LAUNCH_MODE=broad_launch`
- `backend_green=green`
- `harness_green=green`
- `shim_green=green`
- `provider_green=green`
- `remix_green=green`
- `provider_source=external_provider`
- deployed HTTP smoke for all enabled routes with `external_provider` evidence
- `required_field_miss_count=0`
- `under_length_miss_count=0`
