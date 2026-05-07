# Surface Contract

This repo has one launch-owned product path and two legacy parity surfaces. The contract is here so local gates, CI, deployment docs, and operator language all point at the same evidence.

Machine-readable manifest: [`docs/ops/launch_surfaces.json`](/Users/mohit/EmailDJ/docs/ops/launch_surfaces.json). `make surface-contract` validates this manifest before it checks the Makefile, CI, Render Blueprint handoff, and docs.

## Launch-Owned Surfaces

| Surface | Role | Launch evidence |
|---|---|---|
| `hub-api/` | Backend of record for web generate/remix, SSE, validation, evals, runtime debug, and launch checks | `hub-api/tests`, `hub-api/scripts/checks.sh`, `hub-api/reports/launch/*`, runtime snapshots |
| `web-app/` | Frontend of record for the Remix Studio web app | `web-app/tests`, `npm run check:syntax`, `npm run build`, rendered generate/remix QA |
| `chrome-extension/` | Chrome extension client surface | `chrome-extension/tests`, `npm run check:syntax`, `npm run build`, extension flow QA |
| `render.yaml` | Render Blueprint handoff for the launch Hub API and managed Redis/Postgres resources | Blueprint syntax/static contract check, deployed runtime snapshots, deployed HTTP smoke |

## Legacy Surfaces

| Surface | Role | Rule |
|---|---|---|
| `backend/` | Legacy backend and eval harness retained for explicit parity checks | These surfaces do not produce launch-readiness evidence. Use only `make legacy-backend-test` or the path-scoped legacy workflow. |
| `frontend/` | Legacy frontend retained for explicit parity checks | These surfaces do not produce launch-readiness evidence. Use only `make legacy-frontend-test` or `make legacy-build`. |

## Guardrails

- `make test` and `make build` cover only launch-owned surfaces.
- `make launch-gates-local` starts with `make surface-contract` and then runs primary surface tests, evals, launch check, completion audit, and operator handoff.
- `make render-blueprint-check` is the repo-local Render Blueprint gate. It validates the Hub API service, managed datastore references, pinned launch defaults, and Dashboard-filled secrets without needing Render CLI access.
- `make launch-preflight` is the strict deployed-run operator-input check for `STAGING_BASE_URL`, `PROD_BASE_URL`, `BETA_KEY`, and provider transport.
- `make launch-verify-deployed` is the deployed-service gate: preflight, web-app and Chrome-extension release bundle verification, staging and production runtime snapshots, real-provider smoke, staging Hub API HTTP smoke for `generate,remix`, then launch check.
- `make launch-audit` is the artifact-backed completion readout. It maps A-to-Z launch requirements to current evidence or explicit blockers and never treats proxy green tests as completion by themselves.
- `make launch-handoff` is the operator handoff readout. It turns the current audit/preflight state into paste-safe shell exports, Dashboard values, next commands, and blocker groups without embedding secrets.
- `make launch-verify-web-app` is the web app release gate: tests, syntax, build, and `dist/` release config verification against the deployed Hub API URL and preview-pipeline flag.
- `make launch-verify-extension` is the extension release gate: tests, syntax, build, and `dist/` release config verification against the deployed Hub API URL.
- The repo-root `render.yaml` is the Hub API deployment handoff. It must keep provider-stub mode disabled, use managed Redis/Postgres references, and leave operator-specific origins/beta keys/secrets as Dashboard-filled values.
- The general CI `checks` job runs the surface contract, hub-api checks, web-app tests/build, and chrome-extension tests/build.
- `.github/workflows/eval_regression.yml` is intentionally path-scoped to `backend/**` and named as legacy backend evidence.
- Passing legacy tests can be useful during migration, but it never satisfies launch readiness on its own.

## Operator Read

If a release, launch report, PR, or status update says "green," it must name the launch-owned surface that produced the evidence. If the evidence came from `backend/` or `frontend/`, call it legacy parity evidence and keep it separate from launch readiness.
