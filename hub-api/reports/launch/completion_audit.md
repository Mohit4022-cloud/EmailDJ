# Launch Completion Audit

- Generated at: `2026-05-07T21:49:01.924909Z`
- Final status: `not_complete`
- Launch report recommendation: `Not yet launch-ready`
- Open blocker count: `8`

| Requirement | Status | Evidence | Blockers |
|---|---|---|---|
| `hub_api_full_suite` | `pass` | `backend_green=green`<br>`backend_suite_summary=397 passed in 14.71s` | `none` |
| `live_provider_harness` | `pass` | `provider_green=green`<br>`provider_source=external_provider`<br>`external_provider_cases=10/10` | `none` |
| `lock_and_launch_artifacts` | `pass` | `harness_green=green`<br>`render_blueprint_green=green`<br>`provider_stub_cases=96/96`<br>`launch_report_generated_at=2026-05-07T21:08:43.596966Z` | `none` |
| `deployed_preflight_inputs` | `blocked` | `preflight_ready=False`<br>`required_inputs_present={'STAGING_BASE_URL': False, 'PROD_BASE_URL': False, 'BETA_KEY': False, 'OPENAI_API_KEY': True}`<br>`failure_bucket=operator_input_missing` | `STAGING_BASE_URL`<br>`PROD_BASE_URL`<br>`BETA_KEY` |
| `runtime_snapshots` | `blocked` | `staging_snapshot_missing=True`<br>`production_snapshot_missing=True` | `staging_runtime_snapshot_missing`<br>`production_runtime_snapshot_missing` |
| `pinned_origins_beta_provider` | `blocked` | `web_app_origin_state=unset`<br>`chrome_extension_origin_state=default_dev_placeholder`<br>`beta_keys_state=explicit_pinned`<br>`effective_provider_source=external_provider` | `chrome_extension_origin_not_pinned:default_dev_placeholder`<br>`web_app_origin_not_pinned:unset` |
| `durable_infra` | `blocked` | `redis_config_state=forced_inmemory`<br>`database_config_state=default_local_sqlite`<br>`vector_store_config_state=memory_backend` | `database_not_durable_for_launch_mode:limited_rollout:default_local_sqlite`<br>`redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory`<br>`vector_store_not_durable_for_launch_mode:limited_rollout:memory_backend` |
| `validation_fallback_fail_closed` | `pass` | `validation_fallback_allowed=False`<br>`validation_fallback_policy=dev_only_fail_closed_in_launch_modes` | `none` |
| `deployed_http_smoke` | `blocked` | `required_http_smoke_routes=['generate', 'remix']`<br>`route_gates={'generate': True, 'remix': True, 'preview': False}`<br>`localhost_smoke_provider_source_counts={'provider_stub': 60}`<br>`web_app_client_bundle_usable=False`<br>`web_app_probe_failures=['http_error:401', 'web_app_deployment_requires_auth', 'web_app_deployment_requires_auth_or_vercel_protection_bypass', 'no_same_origin_bundle_assets_found', 'vite_hub_url_not_found_in_bundle', 'vite_preview_pipeline_not_found_in_bundle']` | `http_smoke_external_provider_missing_for_launch_mode:limited_rollout`<br>`web_app_deployment_probe_not_usable`<br>`web_app_deployment_probe:http_error:401`<br>`web_app_deployment_probe:web_app_deployment_requires_auth`<br>`web_app_deployment_probe:web_app_deployment_requires_auth_or_vercel_protection_bypass`<br>`web_app_deployment_probe:no_same_origin_bundle_assets_found`<br>`web_app_deployment_probe:vite_hub_url_not_found_in_bundle` |
| `release_fingerprint_parity` | `blocked` | `release_fingerprint_available=True`<br>`release_fingerprint=git_sha=043906e45907`<br>`runtime_source_used=local_env` | `release_fingerprint_unavailable` |
| `chrome_extension_real_target` | `blocked` | `chrome_extension_origin=chrome-extension://dev`<br>`chrome_extension_origin_state=default_dev_placeholder` | `chrome_extension_origin_not_pinned:default_dev_placeholder` |
| `parallel_stack_story` | `pass` | `launch_owned=['chrome-extension/', 'hub-api/', 'web-app/']`<br>`legacy_explicit_only=['backend/', 'frontend/']`<br>`source=docs/ops/launch_surfaces.json` | `none` |
| `draft_workspace_ux` | `pass` | `web-app/tests/layout-contract.test.js`<br>`web-app/src/components/EmailEditor.js` | `none` |
| `launch_report_recommendation` | `blocked` | `final_recommendation=Not yet launch-ready`<br>`config_blocker_count=6`<br>`error_count=0` | `launch_check_not_ready` |

## A-Z Objective Checklist

| # | Objective | Status | Mapped requirements | Blockers | Note |
|---:|---|---|---|---|---|
| 1 | Fix and keep the hub-api full-suite launch-check failure green. | `pass` | `hub_api_full_suite` | `none` |  |
| 2 | Get a fresh live-provider run green, not just mock/provider-stub. | `pass` | `live_provider_harness` | `none` |  |
| 3 | Re-run lock compliance, parity, adversarial, full eval, and launch checks with fresh artifacts. | `pass` | `lock_and_launch_artifacts` | `none` |  |
| 4 | Capture staging and production runtime snapshots. | `blocked` | `runtime_snapshots` | `staging_runtime_snapshot_missing`<br>`production_runtime_snapshot_missing` |  |
| 5 | Pin real staging/prod origins, beta keys, provider mode, validation fallback policy, and release fingerprints. | `blocked` | `pinned_origins_beta_provider`<br>`validation_fallback_fail_closed`<br>`release_fingerprint_parity` | `chrome_extension_origin_not_pinned:default_dev_placeholder`<br>`web_app_origin_not_pinned:unset`<br>`release_fingerprint_unavailable` |  |
| 6 | Prove web app generate/remix/preset preview against deployed hub-api. | `blocked` | `deployed_http_smoke` | `http_smoke_external_provider_missing_for_launch_mode:limited_rollout`<br>`web_app_deployment_probe_not_usable`<br>`web_app_deployment_probe:http_error:401`<br>`web_app_deployment_probe:web_app_deployment_requires_auth`<br>`web_app_deployment_probe:web_app_deployment_requires_auth_or_vercel_protection_bypass`<br>`web_app_deployment_probe:no_same_origin_bundle_assets_found`<br>`web_app_deployment_probe:vite_hub_url_not_found_in_bundle` | Limited rollout proves generate/remix by default; preview smoke is required only when preview is intentionally enabled. |
| 7 | Prove Chrome extension flow in the real target surface. | `blocked` | `chrome_extension_real_target` | `chrome_extension_origin_not_pinned:default_dev_placeholder` |  |
| 8 | Decide and clean up the parallel stack story. | `pass` | `parallel_stack_story` | `none` |  |
| 9 | Harden durable infra: Redis/Postgres/vector store instead of local/in-memory assumptions. | `blocked` | `durable_infra` | `database_not_durable_for_launch_mode:limited_rollout:default_local_sqlite`<br>`redis_not_durable_for_launch_mode:limited_rollout:forced_inmemory`<br>`vector_store_not_durable_for_launch_mode:limited_rollout:memory_backend` |  |
| 10 | Final UX pass so draft workspace feels primary. | `pass` | `draft_workspace_ux` | `none` |  |

## Source Artifacts

- `launch_report`: `/Users/mohit/EmailDJ/hub-api/reports/launch/latest.json`
- `preflight`: `/Users/mohit/EmailDJ/hub-api/reports/launch/preflight.json`
- `web_app_deployment_probe`: `/Users/mohit/EmailDJ/hub-api/reports/launch/web_app_deployment_probe.json`
- `surface_manifest`: `/Users/mohit/EmailDJ/docs/ops/launch_surfaces.json`
