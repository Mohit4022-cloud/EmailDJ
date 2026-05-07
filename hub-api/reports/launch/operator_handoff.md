# Launch Operator Handoff

- Generated at: `2026-05-07T16:33:25.332690Z`
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

## Commands

```bash
make render-blueprint-check
make launch-preflight
make launch-verify-deployed
make launch-audit
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

## Source Artifacts

- `completion_audit`: `/Users/mohit/EmailDJ/hub-api/reports/launch/completion_audit.json`
- `launch_report`: `/Users/mohit/EmailDJ/hub-api/reports/launch/latest.json`
- `preflight`: `/Users/mohit/EmailDJ/hub-api/reports/launch/preflight.json`
