# Launch Operator Guide

Run from [`hub-api`](/Users/mohit/EmailDJ/hub-api).

## Required env vars

- Common:
  - `CHROME_EXTENSION_ORIGIN`
  - `EMAILDJ_WEB_BETA_KEYS`
  - `REDIS_FORCE_INMEMORY=1` for local verification
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

If credentials are missing, the command fails closed and names the required env var.

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
cd /Users/mohit/EmailDJ/hub-api
source .venv/bin/activate
python -m devtools.http_smoke_runner --mode smoke --flow generate --out debug_runs/smoke/manual
```

Expected summary artifact:
- `debug_runs/smoke/manual/summary.json`

The smoke runner now fails clearly if the localhost server is not healthy.

## Launch-check command

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
python scripts/launch_check.py --from-artifacts
```

With localhost smoke included:

```bash
python scripts/launch_check.py --from-artifacts --localhost-smoke-summary debug_runs/smoke/manual/summary.json
```

Canonical launch artifacts:
- `reports/launch/latest.json`
- `reports/launch/latest.md`

## How to interpret artifacts

- `provider_source=provider_stub`: stub harness only
- `provider_source=provider_shim`: real route path with local fake provider
- `provider_source=external_provider`: actual provider-backed verification exists
- `provider_green=green` only counts when an external-provider artifact exists
- `provider_green=not_run` means no external-provider artifact was produced

## Launch categories

`Stable for MVP launch behind limited rollout` requires:
- `EMAILDJ_LAUNCH_MODE=limited_rollout`
- `backend_green=green`
- `harness_green=green`
- `shim_green=green`
- `remix_green=green`
- `required_field_miss_count=0`
- `under_length_miss_count=0`
- `provider_green` may be `green` or `not_run`

`Stable for broad launch` requires:
- `EMAILDJ_LAUNCH_MODE=broad_launch`
- `backend_green=green`
- `harness_green=green`
- `shim_green=green`
- `provider_green=green`
- `remix_green=green`
- `provider_source=external_provider`
- `required_field_miss_count=0`
- `under_length_miss_count=0`
