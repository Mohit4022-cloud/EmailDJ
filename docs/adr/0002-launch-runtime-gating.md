# ADR-0002: Launch Runtime Gating

- Status: Accepted
- Date: 2026-05-07
- Owners: Backend, Launch Ops
- Related code paths: `hub-api/main.py`, `hub-api/email_generation/remix_engine.py`, `hub-api/email_generation/preset_preview_pipeline.py`, `hub-api/email_generation/runtime_policies.py`, `hub-api/scripts/launch_check.py`
- Related docs: `docs/ops/deployment.md`, `docs/ops/surface_contract.md`, `docs/ops/release_checklist.md`, `docs/policy/control_contract.md`

## Context

EmailDJ now has enough local proof to make launch-mode mistakes more dangerous than helpful. The risky failure mode is not a missing feature; it is a deployment that looks green while still using local assumptions: localhost origins, `dev-beta-key`, provider stubs, in-memory Redis, local SQLite, memory vectors, preview routes exposed unintentionally, or deterministic validation fallback hiding a real provider/validator failure.

The repo also carries legacy surfaces (`backend/`, `frontend/`) beside the launch-owned path. Launch status needs to come from the governed Hub API, web app, Chrome extension, Render Blueprint, and deployed runtime snapshots, not from legacy parity checks.

## Decision

Launch modes are fail-closed at runtime and in launch reporting.

For `limited_rollout` and `broad_launch`, Hub API startup must require:
- real provider mode (`USE_PROVIDER_STUB=0`)
- pinned deployed `WEB_APP_ORIGIN`
- pinned deployed `CHROME_EXTENSION_ORIGIN`
- non-dev `EMAILDJ_WEB_BETA_KEYS`
- explicit positive `EMAILDJ_WEB_RATE_LIMIT_PER_MIN`
- managed `REDIS_URL`
- managed Postgres `DATABASE_URL`
- `VECTOR_STORE_BACKEND=pgvector`

For `limited_rollout`, the preset preview route remains disabled unless the route is intentionally enabled outside the limited-rollout gate.

Deterministic validation fallback is allowed only in local/dev mode. Production-like app environments and launch modes must re-raise validation failures after repair attempts so operators see the failure instead of a deterministic rescue draft.

The launch-owned surface contract is pinned in `docs/ops/launch_surfaces.json` and enforced by `make surface-contract`. Legacy `backend/` and `frontend/` evidence remains useful for parity checks, but it cannot satisfy launch readiness.

## Rationale

- Launch readiness should prove the deployed operating path, not a local or mock approximation.
- Startup failure is cheaper and clearer than accepting traffic with local infrastructure, unsafe origins, or provider stubs.
- Deterministic validation fallback is useful for local debugging but dangerous in launch modes because it can hide model, prompt, and validator failures.
- A machine-readable surface manifest gives CI, docs, and status reporting one source of truth for which surfaces produce launch evidence.

## Alternatives Considered

1. **Warn-only launch misconfiguration** — rejected because operators could miss warnings while the service accepts traffic.
2. **Allow deterministic fallback in limited rollout** — rejected because limited rollout is where we need clean provider/validator evidence most.
3. **Treat legacy backend/frontend tests as launch evidence** — rejected because those surfaces no longer represent the primary deployed user path.

## Consequences

- Positive: launch-mode environments fail before serving traffic when durable infra, origins, beta keys, provider mode, or vector storage are unsafe.
- Positive: launch reports distinguish real blockers from local proof and make missing staging/prod evidence explicit.
- Positive: the launch-owned surface decision is now testable through `make surface-contract`.
- Negative: local `.env` values that used to start in permissive modes may now fail in `limited_rollout` unless they are true deployed-service values.
- Risk mitigation: local dev remains available under `EMAILDJ_LAUNCH_MODE=dev`; Render Blueprint and launch preflight document the exact deployed inputs to provide.

## Rollout / Verification

- Required config changes:
  - Set deployed `WEB_APP_ORIGIN`, `CHROME_EXTENSION_ORIGIN`, `EMAILDJ_WEB_BETA_KEYS`, and `EMAILDJ_WEB_RATE_LIMIT_PER_MIN`.
  - Provision managed Redis/Postgres and set `REDIS_URL`, `DATABASE_URL`, and `VECTOR_STORE_BACKEND=pgvector`.
  - Keep `USE_PROVIDER_STUB=0` and set the provider API key for `EMAILDJ_REAL_PROVIDER`.
- Required tests/gates:
  - `make surface-contract`
  - `make render-blueprint-check`
  - `make launch-preflight`
  - `make launch-verify-deployed`
  - `hub-api/tests/test_generation_env_validation.py`
  - `hub-api/tests/test_ctco_validation.py`
  - `hub-api/tests/test_launch_check.py`
- Observability signals:
  - `hub-api/reports/launch/latest.json`
  - `/web/v1/debug/config`
  - staging and production runtime snapshots under `hub-api/reports/launch/runtime_snapshots/`

## Follow-up

- Capture staging and production runtime snapshots after deployed Hub API URLs and beta keys exist.
- Run deployed HTTP smoke against staging with `external_provider` evidence.
- Promote the Render Blueprint from limited rollout only after durable infra and origin pins are proven in launch reports.
