# Surface Contract

This repo has one launch-owned product path and two legacy parity surfaces. The contract is here so local gates, CI, deployment docs, and operator language all point at the same evidence.

## Launch-Owned Surfaces

| Surface | Role | Launch evidence |
|---|---|---|
| `hub-api/` | Backend of record for web generate/remix, SSE, validation, evals, runtime debug, and launch checks | `hub-api/tests`, `hub-api/scripts/checks.sh`, `hub-api/reports/launch/*`, runtime snapshots |
| `web-app/` | Frontend of record for the Remix Studio web app | `web-app/tests`, `npm run check:syntax`, `npm run build`, rendered generate/remix QA |
| `chrome-extension/` | Chrome extension client surface | `chrome-extension/tests`, `npm run check:syntax`, `npm run build`, extension flow QA |

## Legacy Surfaces

| Surface | Role | Rule |
|---|---|---|
| `backend/` | Legacy backend and eval harness retained for explicit parity checks | These surfaces do not produce launch-readiness evidence. Use only `make legacy-backend-test` or the path-scoped legacy workflow. |
| `frontend/` | Legacy frontend retained for explicit parity checks | These surfaces do not produce launch-readiness evidence. Use only `make legacy-frontend-test` or `make legacy-build`. |

## Guardrails

- `make test` and `make build` cover only launch-owned surfaces.
- `make launch-gates-local` starts with `make surface-contract` and then runs primary surface tests, evals, and launch check.
- The general CI `checks` job runs the surface contract, hub-api checks, web-app tests/build, and chrome-extension tests/build.
- `.github/workflows/eval_regression.yml` is intentionally path-scoped to `backend/**` and named as legacy backend evidence.
- Passing legacy tests can be useful during migration, but it never satisfies launch readiness on its own.

## Operator Read

If a release, launch report, PR, or status update says "green," it must name the launch-owned surface that produced the evidence. If the evidence came from `backend/` or `frontend/`, call it legacy parity evidence and keep it separate from launch readiness.
