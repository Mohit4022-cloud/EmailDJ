# Launch Check

- Generated at: `2026-03-17T23:09:41.074361Z`
- Launch mode: `limited_rollout`
- Final recommendation: `Not yet launch-ready`
- Hard freshness threshold (hours): `72`
- Recommended freshness threshold (hours): `48`

| Field | Value |
|---|---|
| backend_green | `red` |
| harness_green | `red` |
| shim_green | `red` |
| provider_green | `red` |
| remix_green | `red` |
| provider_source | `external_provider` |
| required_field_miss_count | 96 |
| under_length_miss_count | 0 |
| claims_policy_intervention_count | 0 |

## Top Violation Codes

- `OFFER_MISSING`: 96

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
- `preview_pipeline_enabled`: `False`
- `route_gates`: `{"generate": true, "preview": false, "remix": true}`
- `route_gate_sources`: `{"generate": "launch_mode:limited_rollout", "preview": "launch_mode:limited_rollout", "remix": "launch_mode:limited_rollout"}`

## Preview Route Invariant

- `preview_enabled`: `False`
- `preview_gate_source`: `launch_mode:limited_rollout`
- `limited_rollout_blocker`: `none`

## Artifact Freshness And Provenance

- `backend` path=`/Users/mohit/EmailDJ/hub-api/reports/launch/backend_suite.json` timestamp=`2026-03-07T22:01:09.442759Z` age_hours=`241.14` stale=`True` malformed=`False` schema_incomplete=`False` missing=`False`
- `provider_stub_harness` path=`/Users/mohit/EmailDJ/hub-api/reports/provider_stub/latest.json` timestamp=`2026-03-07T22:01:10.112801Z` age_hours=`241.14` stale=`True` malformed=`False` schema_incomplete=`False` missing=`False`
- `external_provider_harness` path=`/Users/mohit/EmailDJ/hub-api/reports/external_provider/latest.json` timestamp=`2026-03-10T03:22:16.383352Z` age_hours=`187.79` stale=`True` malformed=`False` schema_incomplete=`False` missing=`False`
- `provider_shim_capture` path=`/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/provider_shim/staging_compare/summary.json` timestamp=`2026-03-10T03:22:03.047576Z` age_hours=`187.79` stale=`True` malformed=`False` schema_incomplete=`False` missing=`False`
- `external_provider_capture` path=`/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/external_provider/verification/summary.json` timestamp=`2026-03-10T03:22:14.703519Z` age_hours=`187.79` stale=`True` malformed=`False` schema_incomplete=`False` missing=`False`
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

## Config Blockers

- `chrome_extension_origin_not_pinned:default_dev_placeholder`
- `web_app_origin_not_pinned:unset`

## Config Warnings

- `production_runtime_snapshot_missing`
- `release_fingerprint_unavailable`
- `runtime_parity_evaluated_from_local_env_only`
- `staging_runtime_snapshot_missing`

## Artifact Sources

- `backend`: `/Users/mohit/EmailDJ/hub-api/reports/launch/backend_suite.json`
- `provider_stub_harness`: `/Users/mohit/EmailDJ/hub-api/reports/provider_stub/latest.json`
- `external_provider_harness`: `/Users/mohit/EmailDJ/hub-api/reports/external_provider/latest.json`
- `provider_shim_capture`: `/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/provider_shim/staging_compare/summary.json`
- `external_provider_capture`: `/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/external_provider/verification/summary.json`
- `localhost_smoke`: `missing`
- `staging_runtime_snapshot`: `/Users/mohit/EmailDJ/hub-api/reports/launch/runtime_snapshots/staging.json`
- `production_runtime_snapshot`: `/Users/mohit/EmailDJ/hub-api/reports/launch/runtime_snapshots/production.json`

## Errors

- `backend:stale:/Users/mohit/EmailDJ/hub-api/reports/launch/backend_suite.json`
- `provider_stub_harness:stale:/Users/mohit/EmailDJ/hub-api/reports/provider_stub/latest.json`
- `external_provider_harness:stale:/Users/mohit/EmailDJ/hub-api/reports/external_provider/latest.json`
- `provider_shim_capture:stale:/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/provider_shim/staging_compare/summary.json`
- `external_provider_capture:stale:/Users/mohit/EmailDJ/hub-api/debug_runs/launch_ops/external_provider/verification/summary.json`

## Operator Next Step

- Capture the staging hub-api runtime snapshot using `staging` backend URL (`$STAGING_BASE_URL`) and a `BETA_KEY` value present in deployed `EMAILDJ_WEB_BETA_KEYS`: `./.venv/bin/python scripts/capture_runtime_snapshot.py --label staging --url "$STAGING_BASE_URL" --header "x-emaildj-beta-key: $BETA_KEY"`
- Capture the production hub-api runtime snapshot using `production` backend URL (`$PROD_BASE_URL`) and a `BETA_KEY` value present in deployed `EMAILDJ_WEB_BETA_KEYS`: `./.venv/bin/python scripts/capture_runtime_snapshot.py --label production --url "$PROD_BASE_URL" --header "x-emaildj-beta-key: $BETA_KEY"`
