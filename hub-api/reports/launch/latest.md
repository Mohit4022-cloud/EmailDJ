# Launch Check

- Generated at: `2026-05-07T04:57:23.991102Z`
- Launch mode: `limited_rollout`
- Final recommendation: `Not yet launch-ready`
- Hard freshness threshold (hours): `72`
- Recommended freshness threshold (hours): `48`

| Field | Value |
|---|---|
| backend_green | `green` |
| harness_green | `green` |
| shim_green | `green` |
| provider_green | `green` |
| remix_green | `green` |
| provider_source | `external_provider` |
| required_field_miss_count | 0 |
| under_length_miss_count | 0 |
| claims_policy_intervention_count | 0 |

## Top Violation Codes

- None

## Release Fingerprint Parity

- `runtime_source_used`: `local_env`
- `staging`: `{"build_id": null, "git_sha": null, "image_tag": null, "release_version": null}`
- `production`: `{}`
- `comparison_fields`: `[]`

## Resolved Runtime Path

- `runtime_source_used`: `local_env`
- `app_env`: `staging`
- `runtime_mode`: `real`
- `configured_quick_generate_mode`: `real`
- `effective_quick_generate_mode`: `real`
- `provider_stub_enabled`: `False`
- `real_provider_preference`: `openai`
- `effective_provider_source`: `external_provider`
- `effective_provider_model_identifier`: `openai/gpt-5-nano`
- `validation_fallback_allowed`: `False`
- `validation_fallback_policy`: `dev_only_fail_closed_in_launch_modes`
- `preview_pipeline_enabled`: `False`
- `route_gates`: `{"generate": true, "preview": false, "remix": true}`
- `route_gate_sources`: `{"generate": "launch_mode:limited_rollout", "preview": "launch_mode:limited_rollout", "remix": "launch_mode:limited_rollout"}`

## Preview Route Invariant

- `preview_enabled`: `False`
- `preview_gate_source`: `launch_mode:limited_rollout`
- `limited_rollout_blocker`: `none`

## Artifact Freshness And Provenance

- `backend` path=`/Users/mohit/EmailDJ/hub-api/reports/launch/backend_suite.json` timestamp=`2026-05-07T04:25:56Z` age_hours=`0.52` stale=`False` malformed=`False` schema_incomplete=`False` missing=`False`
- `provider_stub_harness` path=`/Users/mohit/EmailDJ/hub-api/reports/provider_stub/latest.json` timestamp=`2026-05-07T04:15:46.581743Z` age_hours=`0.69` stale=`False` malformed=`False` schema_incomplete=`False` missing=`False`
- `external_provider_harness` path=`/Users/mohit/EmailDJ/hub-api/reports/external_provider/latest.json` timestamp=`2026-05-07T04:08:44.145741Z` age_hours=`0.81` stale=`False` malformed=`False` schema_incomplete=`False` missing=`False`
- `provider_shim_capture` path=`/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/provider_shim/20260507T033814Z/summary.json` timestamp=`2026-05-07T03:38:14.704193Z` age_hours=`1.32` stale=`False` malformed=`False` schema_incomplete=`False` missing=`False`
- `external_provider_capture` path=`/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/external_provider/20260507T033921Z/summary.json` timestamp=`2026-05-07T03:39:52.319820Z` age_hours=`1.29` stale=`False` malformed=`False` schema_incomplete=`False` missing=`False`
- `localhost_smoke` path=`missing` timestamp=`missing` age_hours=`n/a` stale=`False` malformed=`False` schema_incomplete=`False` missing=`True`
- `staging_runtime_snapshot` path=`/Users/mohit/EmailDJ/hub-api/reports/launch/runtime_snapshots/staging.json` timestamp=`missing` age_hours=`n/a` stale=`False` malformed=`False` schema_incomplete=`False` missing=`True`
- `production_runtime_snapshot` path=`/Users/mohit/EmailDJ/hub-api/reports/launch/runtime_snapshots/production.json` timestamp=`missing` age_hours=`n/a` stale=`False` malformed=`False` schema_incomplete=`False` missing=`True`

## Origin And Beta-Key Safety

- `chrome_extension_origin`: `chrome-extension://dev`
- `chrome_extension_origin_state`: `default_dev_placeholder`
- `web_app_origin`: `unset`
- `web_app_origin_state`: `unset`
- `beta_keys_state`: `explicit_pinned`
- `web_rate_limit_per_min`: `300`
- `web_rate_limit_source`: `explicit_env`

## Durable Infra Readiness

- `redis_config_state`: `forced_inmemory`
- `database_config_state`: `default_local_sqlite`
- `vector_store_config_state`: `memory_backend`
- `vector_store_backend`: `memory`

## Config Blockers

- `chrome_extension_origin_not_pinned:default_dev_placeholder`
- `redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory`
- `web_app_origin_not_pinned:unset`

## Config Warnings

- `database_not_durable:default_local_sqlite`
- `production_runtime_snapshot_missing`
- `release_fingerprint_unavailable`
- `runtime_parity_evaluated_from_local_env_only`
- `staging_runtime_snapshot_missing`
- `vector_store_not_durable:memory_backend`

## Artifact Sources

- `backend`: `/Users/mohit/EmailDJ/hub-api/reports/launch/backend_suite.json`
- `provider_stub_harness`: `/Users/mohit/EmailDJ/hub-api/reports/provider_stub/latest.json`
- `external_provider_harness`: `/Users/mohit/EmailDJ/hub-api/reports/external_provider/latest.json`
- `provider_shim_capture`: `/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/provider_shim/20260507T033814Z/summary.json`
- `external_provider_capture`: `/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/external_provider/20260507T033921Z/summary.json`
- `localhost_smoke`: `missing`
- `staging_runtime_snapshot`: `/Users/mohit/EmailDJ/hub-api/reports/launch/runtime_snapshots/staging.json`
- `production_runtime_snapshot`: `/Users/mohit/EmailDJ/hub-api/reports/launch/runtime_snapshots/production.json`

## Operator Next Steps

- Set `WEB_APP_ORIGIN` to the deployed web-app origin for the target launch environment, then re-capture staging and production runtime snapshots.
- Set `CHROME_EXTENSION_ORIGIN` to the deployed Chrome extension origin (`chrome-extension://<extension-id>`), then re-capture staging and production runtime snapshots.
- Provision managed Redis for the launch environment, set `REDIS_URL`, and ensure `REDIS_FORCE_INMEMORY` is unset or `0` before re-running launch checks.
- Run the guarded localhost smoke against the intended Hub API process with `EMAILDJ_CONFIRM_LOCALHOST_SMOKE=1 make localhost-smoke`, then rerun `make launch-check`.
- Capture the staging hub-api runtime snapshot using `staging` backend URL (`$STAGING_BASE_URL`) and a `BETA_KEY` value present in deployed `EMAILDJ_WEB_BETA_KEYS`: `./.venv/bin/python scripts/capture_runtime_snapshot.py --label staging --url "$STAGING_BASE_URL" --header "x-emaildj-beta-key: $BETA_KEY"`
- Capture the production hub-api runtime snapshot using `production` backend URL (`$PROD_BASE_URL`) and a `BETA_KEY` value present in deployed `EMAILDJ_WEB_BETA_KEYS`: `./.venv/bin/python scripts/capture_runtime_snapshot.py --label production --url "$PROD_BASE_URL" --header "x-emaildj-beta-key: $BETA_KEY"`
