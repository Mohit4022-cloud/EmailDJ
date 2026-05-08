# Launch Operator Handoff

- Generated at: `2026-05-08T22:27:09.645737Z`
- Current completion status: `not_complete`
- Launch recommendation: `Not yet launch-ready`
- Preflight ready: `False`
- Provider: `openai`
- Provider env: `OPENAI_API_KEY`
- Evidence snapshot: `point_in_time_snapshot`
- Snapshot refresh command: `make launch-probe-web-app && make launch-audit`
- Snapshot contract: Checked-in launch reports are evidence snapshots, not proof of the current deployed HEAD. After every target commit deploy, Vercel deployment change, or deployed web-app input change, rerun make launch-probe-web-app and make launch-audit in the operator session before treating the report as launch proof. Report-only snapshot commits may advance git SHA without invalidating the deployed web-app probe.
- Currentness blockers: `none`

## Shell Exports

```bash
export STAGING_BASE_URL="https://<staging-hub-api-root>"
export PROD_BASE_URL="https://<prod-hub-api-root>"
export BETA_KEY="<one-non-dev-beta-key-from-EMAILDJ_WEB_BETA_KEYS>"
export OPENAI_API_KEY="<openai-api-key>"
export VERCEL_AUTOMATION_BYPASS_SECRET="<vercel-automation-bypass-secret>"
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

## Deployed Gate Target Alignment

- Status: `enforced_by_make_launch_verify_deployed`
- Hub URL: `EMAILDJ_EXPECTED_HUB_URL` must match `STAGING_BASE_URL`
- Beta key: `EMAILDJ_EXPECTED_BETA_KEY` must match `BETA_KEY`
- Failure policy: The full deployed gate exits before bundle verification if release-bundle overrides point at a different Hub URL or beta key than the staging runtime proof target.
- Narrow verifiers for intentional drift: `make launch-verify-web-app`, `make launch-verify-extension`

## Deployed Smoke Flow Contract

- Env: `EMAILDJ_DEPLOYED_SMOKE_FLOWS`
- Default: `generate,remix`
- Valid flows: `generate`, `remix`, `preview`
- Preview policy: Use generate,remix,preview only when the staging preview route is intentionally enabled.
- Failure policy: make launch-verify-deployed exits before deployed smoke artifacts are created if the flow list is empty or contains an invalid flow.

## Launch Command Defaults

```bash
export EMAILDJ_DEPLOYED_SMOKE_FLOWS="generate,remix"
```

| Name | Applies to | Clears launch blockers | Note |
|---|---|---|---|
| `EMAILDJ_DEPLOYED_SMOKE_FLOWS` | `make launch-verify-deployed` | `False` | Default limited rollout smoke covers generate and remix; add preview only when intentionally enabled. |

## Discovered Deployment Metadata

- Candidate WEB_APP_ORIGIN: `https://email-2xke17n6u-mohits-projects-e629a988.vercel.app`
- Usable as WEB_APP_ORIGIN candidate: `True`
- Clears launch blockers: `False`
- Operator note: Deployment metadata only identifies candidate web origins. It does not clear launch blockers until the Hub API deployment pins WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, beta keys, provider mode, and fresh runtime snapshots.

| Deployment | Environment | SHA | Vercel origin |
|---|---|---|---|
| `4622366329` | `Preview` | `4dd98263898214bc9723e7679ef3ac43f9c52bf9` | `https://email-2xke17n6u-mohits-projects-e629a988.vercel.app` |

## Web App Deployment Probe

- Web app URL: `https://email-2xke17n6u-mohits-projects-e629a988.vercel.app`
- Client bundle usable: `False`
- Detected VITE_HUB_URL: `none`
- Detected VITE_PRESET_PREVIEW_PIPELINE: `none`
- Clears launch blockers: `False`

Failures:
- `http_error:401`
- `web_app_deployment_requires_auth`
- `web_app_deployment_requires_auth_or_vercel_protection_bypass`
- `vercel_protection_bypass_secret_missing`
- `no_same_origin_bundle_assets_found`
- `vite_hub_url_not_found_in_bundle`
- `vite_preview_pipeline_not_found_in_bundle`

## Blocked Evidence Refresh

### `web_app_deployment_probe_readout`

- When: Use only while the web-app deployment is still auth/protection blocked and the operator needs a fresh artifact readout before the strict launch gate can pass.
- Evidence: hub-api/reports/launch/web_app_deployment_probe.json records probe_exit_policy=nonblocking_artifact_refresh and client_bundle_usable remains false until the strict probe succeeds.

```bash
make launch-probe-web-app-readout
make launch-audit
make launch-handoff
make launch-unblock-inputs
```


## Commands

```bash
make render-blueprint-check
make launch-preflight
make launch-verify-deployed
make launch-probe-web-app
make launch-audit
make launch-handoff
make launch-unblock-inputs
```

## Open Blockers

- `deployed_preflight_inputs`: `STAGING_BASE_URL`, `PROD_BASE_URL`, `VERCEL_AUTOMATION_BYPASS_SECRET`
- `runtime_snapshots`: `staging_runtime_snapshot_missing`, `production_runtime_snapshot_missing`
- `pinned_origins_beta_provider`: `chrome_extension_origin_not_pinned:default_dev_placeholder`, `web_app_origin_not_pinned:unset`
- `durable_infra`: `database_not_durable_for_launch_mode:limited_rollout:default_local_sqlite`, `redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory`, `vector_store_not_durable_for_launch_mode:limited_rollout:memory_backend`
- `deployed_http_smoke`: `http_smoke_external_provider_missing_for_launch_mode:limited_rollout`, `web_app_deployment_probe_not_usable`, `web_app_deployment_probe:http_error:401`, `web_app_deployment_probe:web_app_deployment_requires_auth`, `web_app_deployment_probe:web_app_deployment_requires_auth_or_vercel_protection_bypass`, `web_app_deployment_probe:vercel_protection_bypass_secret_missing`, `web_app_deployment_probe:no_same_origin_bundle_assets_found`
- `release_fingerprint_parity`: `release_fingerprint_parity_not_from_production_runtime_snapshot:local_env`, `release_fingerprint_comparison_fields_missing`
- `chrome_extension_real_target`: `chrome_extension_origin_not_pinned:default_dev_placeholder`
- `launch_report_recommendation`: `launch_check_not_ready`

## Blocker Clearance Plan

| Blocker | Operator action | Evidence to expect |
|---|---|---|
| `deployed_preflight_inputs` | Export `PROD_BASE_URL`, `STAGING_BASE_URL`, `VERCEL_AUTOMATION_BYPASS_SECRET` on the operator machine, confirm BETA_KEY matches one deployed beta key, then run make launch-preflight. | hub-api/reports/launch/preflight.json has ready=true and no missing_inputs. |
| `runtime_snapshots` | Run make launch-verify-deployed after the operator exports are set; it captures staging and production runtime snapshots with the deployed beta key. | hub-api/reports/launch/runtime_snapshots/staging.json and production.json exist and share comparable release fingerprint fields. |
| `pinned_origins_beta_provider` | Set WEB_APP_ORIGIN, CHROME_EXTENSION_ORIGIN, EMAILDJ_WEB_BETA_KEYS, EMAILDJ_REAL_PROVIDER, OPENAI_API_KEY, USE_PROVIDER_STUB=0, and EMAILDJ_WEB_RATE_LIMIT_PER_MIN in the deployment dashboard. | launch latest shows web_app_origin_state=explicit_pinned, chrome_extension_origin_state=explicit_pinned, beta_keys_state=explicit_pinned, and effective_provider_source=external_provider. |
| `durable_infra` | Provision managed Redis and Postgres, set REDIS_URL and DATABASE_URL, set VECTOR_STORE_BACKEND=pgvector, and keep REDIS_FORCE_INMEMORY unset or 0. | launch latest shows redis_config_state=external_redis_configured, database_config_state=external_postgres_configured, and vector_store_config_state=pgvector_configured. |
| `deployed_http_smoke` | Run make launch-verify-deployed against staging. Default limited rollout proves generate and remix; use EMAILDJ_DEPLOYED_SMOKE_FLOWS=generate,remix,preview only when preview is intentionally enabled. | hub-api/debug_runs/smoke/deployed/summary.json proves external_provider traffic and green required route coverage. |
| `release_fingerprint_parity` | Capture both staging and production runtime snapshots from deployed services after release metadata is available. | launch latest has release_fingerprint_parity.runtime_source_used from deployed snapshots and non-empty comparison_fields. |
| `chrome_extension_real_target` | Set CHROME_EXTENSION_ORIGIN to the shipped chrome-extension://<extension-id> and verify the side-panel flow in Chrome. | launch latest shows chrome_extension_origin_state=explicit_pinned and the extension release config passes. |
| `launch_report_recommendation` | After clearing the blocker groups above, rerun make launch-probe-web-app, make launch-audit, make launch-handoff, and make launch-unblock-inputs. | completion_audit.json final_status=complete and launch latest no longer says Not yet launch-ready. |

## Source Artifacts

- `completion_audit`: `/Users/mohit/EmailDJ/hub-api/reports/launch/completion_audit.json`
- `launch_report`: `/Users/mohit/EmailDJ/hub-api/reports/launch/latest.json`
- `preflight`: `/Users/mohit/EmailDJ/hub-api/reports/launch/preflight.json`
- `deployment_discovery`: `/Users/mohit/EmailDJ/hub-api/reports/launch/deployment_discovery.json`
- `web_app_deployment_probe`: `/Users/mohit/EmailDJ/hub-api/reports/launch/web_app_deployment_probe.json`
