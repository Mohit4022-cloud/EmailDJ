# DEPLOYMENT PARITY MATRIX

This document is the operator-facing source of truth for EmailDJ limited-rollout deployment parity.

Validated local prod-like baseline:
- `launch_mode=limited_rollout`
- `final_recommendation=Stable for MVP launch behind limited rollout`
- `provider_source=external_provider`

Use these local validated sources when comparing staging and production:
- `hub-api/.env`
- `hub-api/reports/launch/latest.json`
- `hub-api/reports/external_provider/latest.json`
- `hub-api/reports/provider_stub/latest.json`
- `hub-api/debug_runs/launch_ops/external_provider/verification/summary.json`
- `hub-api/debug_runs/launch_ops/provider_shim/staging_compare/summary.json`
- code defaults in `hub-api/email_generation/runtime_policies.py`, `hub-api/main.py`, and `hub-api/api/middleware/beta_access.py`

| Variable / Input | Expected for `limited_rollout` | Missing Safe? | Local Validated Source | Target Deployment Expected Source | Risky Mismatch |
|---|---|---|---|---|---|
| `APP_ENV` | `staging` on staging, `prod` on production | No | `hub-api/.env` and `launch_check` runtime config | Platform env config, `/web/v1/debug/config` | Falls back to local/dev-like defaults |
| `EMAILDJ_LAUNCH_MODE` | `limited_rollout` explicitly | No | `hub-api/reports/launch/latest.json` | Platform env config, `/web/v1/debug/config` | Host silently depends on `APP_ENV` default |
| `EMAILDJ_ROUTE_GENERATE_ENABLED` | unset or `1` | Only if `EMAILDJ_LAUNCH_MODE=limited_rollout` is explicit | runtime policy defaults | Platform env config, `/web/v1/debug/config` | Explicit `0` disables generate in rollout |
| `EMAILDJ_ROUTE_REMIX_ENABLED` | unset or `1` | Only if `EMAILDJ_LAUNCH_MODE=limited_rollout` is explicit | runtime policy defaults | Platform env config, `/web/v1/debug/config` | Explicit `0` disables remix in rollout |
| `EMAILDJ_ROUTE_PREVIEW_ENABLED` | unset or `0` | Yes when `limited_rollout` is explicit | runtime policy defaults | Platform env config, `/web/v1/debug/config` | Explicit `1` re-enables preview and breaks canonical rollout shape |
| `USE_PROVIDER_STUB` | explicit `0` | No for parity | `hub-api/.env`, launch runtime config | Platform env config, `/web/v1/debug/config` | Stub traffic in non-dev rollout |
| `EMAILDJ_REAL_PROVIDER` | explicit `openai` | Default-safe, parity-risky | `hub-api/.env` | Platform env config, `/web/v1/debug/config` | Provider routing differs from validated run |
| `OPENAI_API_KEY` | present and non-empty | No | local secret presence implied by real harness success | Secret store, startup validation | Real mode fails or preview pipeline fails when enabled |
| `EMAILDJ_QUICK_GENERATE_MODE` | unset or `real` | Yes | local `.env` currently pins `real` | Platform env config, launch report runtime config | Explicit value disagrees with resolved `USE_PROVIDER_STUB` mode |
| `CHROME_EXTENSION_ORIGIN` | explicit non-empty deployed value | No | `hub-api/.env` | Platform env config | App fails startup validation |
| `WEB_APP_ORIGIN` | explicit staging/prod web origin(s) | No for parity | code plus local deployment assumptions | Platform env config, CORS behavior, `/debug/config` warning state | Deployed CORS differs from validated host |
| `EMAILDJ_WEB_BETA_KEYS` | explicit non-default operator key | No for parity | `hub-api/.env` currently uses dev key locally | Platform env config, operator secret handling, live requests | Deployed host accepts default dev key |
| `EMAILDJ_WEB_RATE_LIMIT_PER_MIN` | explicit `300` | No for parity | `hub-api/.env` | Platform env config | Default drift: settings module uses `60`, middleware uses `30` |
| `EMAILDJ_PRESET_PREVIEW_PIPELINE` | unset or `off` on canonical limited-rollout host | Yes | runtime policy defaults, route gates | Platform env config, `/web/v1/debug/config` | Preview pipeline enabled unexpectedly |
| `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL` | `repair` | Default-safe | code default plus validated local behavior | Platform env config or default | Non-canonical enforcement behavior |
| `EMAILDJ_REPAIR_LOOP_ENABLED` | unset or `1` | Yes | code default | Platform env config or default | Unexpected disabled repair loop |
| `EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE` | `1.0` to match validated local state | Default-safe, parity-risky | `hub-api/.env` | Platform env config | Debug bundle sampling differs from validated host |
| `QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD` | `5` | Default-risky for parity | `hub-api/.env` | Platform env config | Alerting cadence diverges |
| `QUICK_PROVIDER_FAILURE_ALERT_STEP` | `5` | Default-risky for parity | `hub-api/.env` | Platform env config | Alerting cadence diverges |
| `reports/external_provider/latest.json` | present, fresh, zero failed cases | No | current local validated report | Deployed filesystem artifact path | Launch-check cannot verify real-provider readiness |
| `debug_runs/launch_ops/external_provider/verification/summary.json` | present, fresh, `provider_green=green`, `remix_green=green` | No | current local validated capture | Deployed filesystem artifact path | Real-provider route state not proven |
| `debug_runs/launch_ops/provider_shim/staging_compare/summary.json` | present, fresh, `shim_green=green`, `remix_green=green` | No | current local validated capture | Deployed filesystem artifact path | Shim parity not proven |
| `/web/v1/debug/config` | `runtime_mode=real`, `provider_stub_enabled=false`, `real_provider_preference=openai`, `launch_mode=limited_rollout`, preview off | No | current runtime policy behavior | Live deployed endpoint | Host resolves a different runtime than env review suggested |

High-risk divergence patterns:
- `USE_PROVIDER_STUB=1` with `EMAILDJ_LAUNCH_MODE=limited_rollout` or `broad_launch`
- explicit `EMAILDJ_QUICK_GENERATE_MODE` disagrees with resolved runtime mode
- `EMAILDJ_ROUTE_PREVIEW_ENABLED=1` in canonical limited rollout
- `EMAILDJ_WEB_BETA_KEYS=dev-beta-key` on deployed hosts
- `EMAILDJ_WEB_RATE_LIMIT_PER_MIN` left implicit

# DEPLOYED VERIFICATION FLOW

Run staging first to generate fresh approved artifacts. Treat production as read-only parity verification against the approved staging artifact set.

Use the same Python environment the deployed app uses. In this repo that is `hub-api/.venv/bin/python`.

Staging host, fresh verification:

```bash
cd /path/to/EmailDJ/hub-api
curl -fsS "$STAGING_BASE_URL/"
curl -fsS -H "x-emaildj-beta-key: $BETA_KEY" "$STAGING_BASE_URL/web/v1/debug/config?endpoint=generate&bucket_key=rollout-audit"
curl -fsS -H "x-emaildj-beta-key: $BETA_KEY" "$STAGING_BASE_URL/web/v1/debug/config?endpoint=preview&bucket_key=rollout-audit"
./scripts/eval:full --real
./.venv/bin/python scripts/capture_ui_session.py --provider-path provider_shim --out debug_runs/launch_ops/provider_shim/staging_compare
./.venv/bin/python scripts/capture_ui_session.py --provider-path external_provider --out debug_runs/launch_ops/external_provider/verification
./.venv/bin/python scripts/launch_check.py --from-artifacts --max-age-hours 72
```

Production limited-rollout host, read-only parity verification:

```bash
cd /path/to/EmailDJ/hub-api
curl -fsS "$PROD_BASE_URL/"
curl -fsS -H "x-emaildj-beta-key: $BETA_KEY" "$PROD_BASE_URL/web/v1/debug/config?endpoint=generate&bucket_key=rollout-audit"
curl -fsS -H "x-emaildj-beta-key: $BETA_KEY" "$PROD_BASE_URL/web/v1/debug/config?endpoint=preview&bucket_key=rollout-audit"
./.venv/bin/python scripts/launch_check.py --from-artifacts --max-age-hours 72
```

Expected live outputs:
- `/` returns `{"status":"ok","version":"0.1.0"}`
- `/web/v1/debug/config` shows:
  - `runtime_mode=real`
  - `provider_stub_enabled=false`
  - `real_provider_preference=openai`
  - `launch_mode=limited_rollout`
  - `route_gates.generate=true`
  - `route_gates.remix=true`
  - `route_gates.preview=false`
- `reports/launch/latest.json` shows:
  - `final_recommendation="Stable for MVP launch behind limited rollout"`
  - `provider_source="external_provider"`
  - `config_blockers=[]`
- `reports/external_provider/latest.json` shows:
  - `summary.failed_cases=0`
  - `summary.required_field_miss_count=0`
  - `summary.under_length_miss_count=0`
- `debug_runs/launch_ops/external_provider/verification/summary.json` shows:
  - `launch_gates.provider_green="green"`
  - `launch_gates.remix_green="green"`
- `debug_runs/launch_ops/provider_shim/staging_compare/summary.json` shows:
  - `launch_gates.shim_green="green"`
  - `launch_gates.remix_green="green"`

Artifacts operators should inspect directly:
- `hub-api/reports/launch/latest.json`
- `hub-api/reports/launch/latest.md`
- `hub-api/reports/external_provider/latest.json`
- `hub-api/reports/provider_stub/latest.json`
- `hub-api/debug_runs/launch_ops/external_provider/verification/summary.json`
- `hub-api/debug_runs/launch_ops/provider_shim/staging_compare/summary.json`

# CODE / DOC CHANGES

Files changed by this pass:
- `hub-api/scripts/launch_check.py`
  - Adds resolved runtime-config reporting and narrow config blockers/warnings at the launch-check boundary.
- `hub-api/tests/test_launch_check.py`
  - Covers runtime-config reporting, dotenv precedence, explicit mode mismatch blocking, stub-enabled rollout blocking, and markdown section coverage.
- `hub-api/docs/limited_rollout_deployment_parity.md`
  - Adds the operator matrix, staged verification flow, checklist, rollback triggers, and final judgment reference.

Generation logic confirmation:
- No changes to `backend/app/engine/**`
- No validator weakening
- No CTA-lock, token-floor, or fail-closed behavior changes
- No route-handler behavior changes

# LIMITED-ROLLOUT CHECKLIST

Pre-traffic checklist:
- Confirm staging and production both pin `EMAILDJ_LAUNCH_MODE=limited_rollout`.
- Confirm `USE_PROVIDER_STUB=0` and `EMAILDJ_REAL_PROVIDER=openai` on both hosts.
- Confirm `OPENAI_API_KEY` exists in the deployment secret store.
- Confirm `EMAILDJ_ROUTE_GENERATE_ENABLED` and `EMAILDJ_ROUTE_REMIX_ENABLED` are not disabled.
- Confirm `EMAILDJ_ROUTE_PREVIEW_ENABLED` is unset or `0`.
- Confirm `CHROME_EXTENSION_ORIGIN` and `WEB_APP_ORIGIN` are explicitly set for the deployed host.
- Confirm `EMAILDJ_WEB_BETA_KEYS` is not `dev-beta-key`.
- Confirm `EMAILDJ_WEB_RATE_LIMIT_PER_MIN=300` is pinned explicitly.
- Confirm staging fresh-run artifacts are present and under the `72h` freshness window.
- Confirm `reports/launch/latest.json` has `config_blockers=[]`.
- Confirm production `/web/v1/debug/config` matches staging-approved runtime values.

Pass condition for first controlled traffic:
- Staging fresh verification is green.
- Production read-only parity verification is green.
- `reports/launch/latest.json` ends with `Stable for MVP launch behind limited rollout`.
- External provider harness and external provider capture are both green.
- Preview remains disabled.

Rollback triggers:
- `reports/launch/latest.json` changes to `Not yet launch-ready`
- any `config_blockers` entry appears
- `/web/v1/debug/config` resolves `provider_stub_enabled=true`
- `/web/v1/debug/config` resolves `launch_mode` other than `limited_rollout`
- `/web/v1/debug/config` resolves `route_gates.preview=true` without explicit re-approval
- `summary.failed_cases > 0` in `reports/external_provider/latest.json`
- `provider_green` or `remix_green` turns red in the external provider capture summary
- missing or stale launch artifacts prevent parity confirmation

# FINAL JUDGMENT

Deployment parity is fully specified when all of the following are true:
- staging produces a fresh green artifact set
- production resolves the same runtime config through `/web/v1/debug/config`
- `launch_check.py` reports no config blockers
- the final launch artifact remains `Stable for MVP launch behind limited rollout`

Smallest remaining blocker if launch is not approved:
- Any unresolved difference between deployed runtime config and the validated staging artifact set takes priority over all other checklist items.
