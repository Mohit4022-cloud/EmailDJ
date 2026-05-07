# Launch Operator Handoff

- Generated at: `2026-05-07T21:40:38.321965Z`
- Current completion status: `not_complete`
- Launch recommendation: `Not yet launch-ready`
- Preflight ready: `False`
- Provider: `openai`
- Provider env: `OPENAI_API_KEY`

## Shell Exports

```bash
export STAGING_BASE_URL="https://<staging-hub-api-root>"
export PROD_BASE_URL="https://<prod-hub-api-root>"
export BETA_KEY="<one-non-dev-beta-key-from-EMAILDJ_WEB_BETA_KEYS>"
export EMAILDJ_EXPECTED_HUB_URL="$STAGING_BASE_URL"
export EMAILDJ_EXPECTED_BETA_KEY="$BETA_KEY"
export EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE="off"
export VITE_HUB_URL="$STAGING_BASE_URL"
export VITE_EMAILDJ_BETA_KEY="$BETA_KEY"
export VITE_PRESET_PREVIEW_PIPELINE="off"
```

## Render / Deployment Dashboard Inputs

| Name | Value | Required now |
|---|---|---|
| `EMAILDJ_LAUNCH_MODE` | `limited_rollout` | `True` |
| `EMAILDJ_REAL_PROVIDER` | `openai` | `True` |
| `OPENAI_API_KEY` | `<openai-api-key>` | `True` |
| `WEB_APP_ORIGIN` | `https://<deployed-web-app-origin>` | `True` |
| `CHROME_EXTENSION_ORIGIN` | `chrome-extension://<shipped-extension-id>` | `True` |
| `EMAILDJ_WEB_BETA_KEYS` | `<non-dev-beta-key-1>,<non-dev-beta-key-2>` | `True` |
| `EMAILDJ_WEB_RATE_LIMIT_PER_MIN` | `300` | `True` |
| `USE_PROVIDER_STUB` | `0` | `True` |
| `REDIS_URL` | `<managed-redis-url>` | `True` |
| `DATABASE_URL` | `<managed-postgres-url>` | `True` |
| `VECTOR_STORE_BACKEND` | `pgvector` | `True` |
| `REDIS_FORCE_INMEMORY` | `<unset or 0>` | `True` |

## Discovered Deployment Metadata

- Candidate WEB_APP_ORIGIN: `https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app`
- Usable as WEB_APP_ORIGIN candidate: `True`
- Clears launch blockers: `False`
- Operator note: Deployment metadata only identifies candidate web origins. It does not clear launch blockers until the Hub API deployment pins WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, beta keys, provider mode, and fresh runtime snapshots.

| Deployment | Environment | SHA | Vercel origin |
|---|---|---|---|
| `4614098730` | `Preview` | `4f323ae5ee8530886f267733f85c3c2061d27ca1` | `https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app` |

## Web App Deployment Probe

- Web app URL: `https://email-pbkwcngj2-mohits-projects-e629a988.vercel.app`
- Client bundle usable: `False`
- Detected VITE_HUB_URL: `none`
- Detected VITE_PRESET_PREVIEW_PIPELINE: `none`
- Clears launch blockers: `False`

Failures:
- `http_error:401`
- `no_same_origin_bundle_assets_found`
- `vite_hub_url_not_found_in_bundle`
- `vite_preview_pipeline_not_found_in_bundle`

## Commands

```bash
make render-blueprint-check
make launch-preflight
make launch-verify-deployed
make launch-audit
make launch-discover-deployment
make launch-probe-web-app
make launch-handoff
```

## Open Blockers

- `deployed_preflight_inputs`: `STAGING_BASE_URL`, `PROD_BASE_URL`, `BETA_KEY`
- `runtime_snapshots`: `staging_runtime_snapshot_missing`, `production_runtime_snapshot_missing`
- `pinned_origins_beta_provider`: `chrome_extension_origin_not_pinned:default_dev_placeholder`, `web_app_origin_not_pinned:unset`
- `durable_infra`: `database_not_durable_for_launch_mode:limited_rollout:default_local_sqlite`, `redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory`, `vector_store_not_durable_for_launch_mode:limited_rollout:memory_backend`
- `deployed_http_smoke`: `http_smoke_external_provider_missing_for_launch_mode:limited_rollout`
- `release_fingerprint_parity`: `release_fingerprint_unavailable`
- `chrome_extension_real_target`: `chrome_extension_origin_not_pinned:default_dev_placeholder`
- `launch_report_recommendation`: `launch_check_not_ready`

## Blocker Clearance Plan

| Blocker | Operator action | Evidence to expect |
|---|---|---|
| `deployed_preflight_inputs` | Export STAGING_BASE_URL, PROD_BASE_URL, and BETA_KEY on the operator machine, then run make launch-preflight. | hub-api/reports/launch/preflight.json has ready=true and no missing_inputs. |
| `runtime_snapshots` | Run make launch-verify-deployed after the operator exports are set; it captures staging and production runtime snapshots with the deployed beta key. | hub-api/reports/launch/runtime_snapshots/staging.json and production.json exist and share comparable release fingerprint fields. |
| `pinned_origins_beta_provider` | Set WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, EMAILDJ_WEB_BETA_KEYS, EMAILDJ_REAL_PROVIDER, OPENAI_API_KEY, USE_PROVIDER_STUB=0, and EMAILDJ_WEB_RATE_LIMIT_PER_MIN in the deployment dashboard. | launch latest shows web_app_origin_state=explicit_pinned, chrome_extension_origin_state=explicit_pinned, beta_keys_state=explicit_pinned, and effective_provider_source=external_provider. |
| `durable_infra` | Provision managed Redis and Postgres, set REDIS_URL and DATABASE_URL, set VECTOR_STORE_BACKEND=pgvector, and keep REDIS_FORCE_INMEMORY unset or 0. | launch latest shows redis_config_state=external_redis_configured, database_config_state=external_postgres_configured, and vector_store_config_state=pgvector_configured. |
| `deployed_http_smoke` | Run make launch-verify-deployed against staging. Default limited rollout proves generate and remix; use EMAILDJ_DEPLOYED_SMOKE_FLOWS=generate,remix,preview only when preview is intentionally enabled. | hub-api/debug_runs/smoke/deployed/summary.json proves external_provider traffic and green required route coverage. |
| `release_fingerprint_parity` | Capture both staging and production runtime snapshots from deployed services after release metadata is available. | launch latest has release_fingerprint_parity.runtime_source_used from deployed snapshots and non-empty comparison_fields. |
| `chrome_extension_real_target` | Set CHROME_EXTENSION_ORIGIN to the shipped chrome-extension://<extension-id> and verify the side-panel flow in Chrome. | launch latest shows chrome_extension_origin_state=explicit_pinned and the extension release config passes. |
| `launch_report_recommendation` | After clearing the blocker groups above, rerun make launch-audit and make launch-handoff. | completion_audit.json final_status=complete and launch latest no longer says Not yet launch-ready. |

## Source Artifacts

- `completion_audit`: `/Users/mohit/EmailDJ/hub-api/reports/launch/completion_audit.json`
- `launch_report`: `/Users/mohit/EmailDJ/hub-api/reports/launch/latest.json`
- `preflight`: `/Users/mohit/EmailDJ/hub-api/reports/launch/preflight.json`
- `deployment_discovery`: `/Users/mohit/EmailDJ/hub-api/reports/launch/deployment_discovery.json`
- `web_app_deployment_probe`: `/Users/mohit/EmailDJ/hub-api/reports/launch/web_app_deployment_probe.json`
