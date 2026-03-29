# LIMITED ROLLOUT DEPLOYMENT PARITY RUNBOOK

This document is the operator runbook for EmailDJ limited-rollout deployment parity.

Repo-side readiness is not the same as deployed-env readiness.

- Repo-side readiness means the checker, artifacts, docs, and runtime debug surface can evaluate deployed parity correctly.
- Deployed-env readiness requires fresh staging and production `/web/v1/debug/config` snapshots plus fresh launch artifacts from the actual target hosts.

Before touching launch artifacts, operators should run `scripts/launch_preflight.py` from the same host. It checks required env inputs and provider transport and writes:

- `hub-api/reports/launch/preflight.json`
- `hub-api/reports/launch/preflight.md`

## Launch Rule

Limited-rollout launch readiness must be tied to the exact deployed runtime.

That means final launch judgment now depends on:

- fresh launch artifacts
- resolved runtime fields from `/web/v1/debug/config`
- release fingerprint parity between approved staging and production
- preview staying off in `limited_rollout`
- pinned non-dev origins and non-default beta keys

If staging or production runtime snapshots are missing, stale, or schema-incomplete, `scripts/launch_check.py` can still report repo-side readiness, but deployed parity is not yet verified.

## Runtime Snapshot Paths

Operators should capture runtime snapshots with `scripts/capture_runtime_snapshot.py`, which writes to these exact paths by default:

- `hub-api/reports/launch/runtime_snapshots/staging.json`
- `hub-api/reports/launch/runtime_snapshots/production.json`

The checker uses those paths by default, with optional CLI overrides.

## Release Fingerprint Requirement

The runtime debug surface exposes these release identity fields when available:

- `git_sha`
- `build_id`
- `image_tag`
- `release_version`
- `release_fingerprint`

Release fingerprint precedence:

- `git_sha`: `EMAILDJ_GIT_SHA`, `GITHUB_SHA`, then repo git metadata if available
- `build_id`: `EMAILDJ_BUILD_ID`, `BUILD_ID`
- `image_tag`: `EMAILDJ_IMAGE_TAG`, `IMAGE_TAG`
- `release_version`: `EMAILDJ_RELEASE_VERSION`

Canonical fingerprint format:

- `git_sha=<...>|build_id=<...>|image_tag=<...>|release_version=<...>`

Launch rule:

- if staging and production expose overlapping fingerprint fields and any value differs, launch is blocked
- if fingerprint data is unavailable, launch_check warns explicitly instead of silently passing provenance

Deployment expectation:

- production should expose at least one stable fingerprint field
- if git metadata is not available on-host, deployment must inject one of the env-backed identifiers above

## Resolved Runtime Field Meanings

These `/web/v1/debug/config` fields are used for parity:

- `runtime_mode`: existing runtime mode surface
- `configured_quick_generate_mode`: operator preference from env, if explicitly set
- `effective_quick_generate_mode`: resolved runtime mode after policy resolution
- `provider_stub_enabled`: resolved stub toggle
- `real_provider_preference`: configured real-provider preference
- `effective_provider_source`: actual resolved provider path, `external_provider` or `provider_stub`
- `effective_provider`: resolved primary provider
- `effective_model`: resolved primary model
- `effective_model_identifier`: `<provider>/<model>`
- `route_gates`
- `route_gate_sources`

Configured vs resolved matters:

- `real_provider_preference=openai` does not prove the runtime is external
- `effective_provider_source=external_provider` is the resolved runtime proof needed for limited rollout
- `configured_quick_generate_mode` can disagree with `effective_quick_generate_mode`; that disagreement is a blocker

## Exactness Rules

### Origins

The debug surface classifies origin fields as:

- `unset`
- `default_dev_placeholder`
- `explicit_pinned`

Rules:

- `CHROME_EXTENSION_ORIGIN=""` => `unset`
- `CHROME_EXTENSION_ORIGIN=chrome-extension://dev` => `default_dev_placeholder`
- any other extension origin => `explicit_pinned`
- empty `WEB_APP_ORIGIN` => `unset`
- localhost-only `WEB_APP_ORIGIN` values => `default_dev_placeholder`
- deployed host origins => `explicit_pinned`

Limited rollout is not ready if web or extension origins are `unset` or `default_dev_placeholder`.

### Beta Keys

The debug surface classifies beta keys as:

- `unset`
- `default_dev_placeholder`
- `explicit_pinned`

Rules:

- empty `EMAILDJ_WEB_BETA_KEYS` => `unset`
- any value containing `dev-beta-key` => `default_dev_placeholder`
- otherwise => `explicit_pinned`

Limited rollout is not ready if beta keys are unset or default/dev.

### Rate Limit Drift

The checker surfaces:

- `web_rate_limit_per_min`
- `web_rate_limit_source`

Source values:

- `explicit_env`
- `middleware_default_30`

Launch rule:

- default drift remains warning-only, but it must be explicit
- limited-rollout operators should pin `EMAILDJ_WEB_RATE_LIMIT_PER_MIN=300`
- the warning exists because settings and middleware defaults have historically drifted

## Preview Route Invariant

In `limited_rollout`, preview must stay off unless there is an explicit, documented policy exception outside this runbook.

Current launch rule:

- `route_gates.preview=true` in `limited_rollout` is a blocker
- this is enforced from resolved runtime snapshot data, not just env intent

The launch markdown now includes a dedicated `Preview Route Invariant` section so this state is obvious during operator review.

## Freshness Expectations

Two freshness windows exist:

- hard threshold: `--max-age-hours`, default `72`
- recommended launch-day threshold: `--recommended-max-age-hours`, default `48`

Meaning:

- older than 48h but within the hard threshold => warning
- older than the hard threshold => stale artifact, launch not ready

Artifacts covered:

- `reports/launch/backend_suite.json`
- `reports/provider_stub/latest.json`
- `reports/external_provider/latest.json`
- latest provider-shim capture summary
- latest external-provider capture summary
- optional localhost smoke summary
- staging runtime snapshot
- production runtime snapshot

## Operator Flow

Run staging first to produce the approved artifact set. Treat production as read-only parity verification against that approved staging reference.

Use the same Python environment the deployed app uses. In this repo that is usually `hub-api/.venv/bin/python`.

### 1. Staging verification

```bash
cd /path/to/EmailDJ/hub-api
./.venv/bin/python scripts/launch_preflight.py
curl -fsS "$STAGING_BASE_URL/"
./.venv/bin/python scripts/capture_runtime_snapshot.py \
  --label staging \
  --url "$STAGING_BASE_URL" \
  --header "x-emaildj-beta-key: $BETA_KEY"

./scripts/eval:full --real
./.venv/bin/python scripts/capture_ui_session.py \
  --provider-path provider_shim \
  --out debug_runs/launch_ops/provider_shim/staging_compare
./.venv/bin/python scripts/capture_ui_session.py \
  --provider-path external_provider \
  --out debug_runs/launch_ops/external_provider/verification

./.venv/bin/python scripts/launch_check.py --from-artifacts
```

### 2. Production read-only parity verification

```bash
cd /path/to/EmailDJ/hub-api
curl -fsS "$PROD_BASE_URL/"
./.venv/bin/python scripts/capture_runtime_snapshot.py \
  --label production \
  --url "$PROD_BASE_URL" \
  --header "x-emaildj-beta-key: $BETA_KEY"

./.venv/bin/python scripts/launch_check.py --from-artifacts
```

If these runtime snapshots are absent, stale, or schema-incomplete, launch_check can only judge repo-side readiness plus artifact health. That is not sufficient to claim deployed-env readiness.

## Capture Command Rules

Use `scripts/capture_runtime_snapshot.py` for all operator captures.
Use `scripts/launch_preflight.py` before any real-provider launch verification run.

- `--label staging` writes to `reports/launch/runtime_snapshots/staging.json`
- `--label production` writes to `reports/launch/runtime_snapshots/production.json`
- `--url` may be either a base host or a full `/web/v1/debug/config` URL
- use repeatable `--header` values for request headers; the standard rollout example is `x-emaildj-beta-key`

The capture script validates the runtime snapshot before writing it. A non-200 response, invalid JSON payload, or schema-incomplete parity payload is a hard failure and should be fixed before trusting the snapshot.
The preflight script blocks early on missing `STAGING_BASE_URL`, `PROD_BASE_URL`, `BETA_KEY`, missing provider credentials, and provider transport failures such as DNS or timeout errors.

## Expected Runtime Snapshot Shape

For a healthy limited-rollout host, `/web/v1/debug/config` should resolve to:

- `launch_mode=limited_rollout`
- `effective_quick_generate_mode=real`
- `provider_stub_enabled=false`
- `effective_provider_source=external_provider`
- `route_gates.generate=true`
- `route_gates.remix=true`
- `route_gates.preview=false`
- `chrome_extension_origin_state=explicit_pinned`
- `web_app_origin_state=explicit_pinned`
- `beta_keys_state=explicit_pinned`
- `web_rate_limit_source=explicit_env`

## Blocker And Warning Table

| Type | Code / Condition | Meaning |
|---|---|---|
| Blocker | `provider_stub_enabled_for_launch_mode:limited_rollout` | Stubbed traffic in rollout runtime |
| Blocker | `configured_quick_generate_mode_mismatch:<configured>-><effective>` | Env preference disagrees with resolved runtime mode |
| Blocker | `resolved_provider_source_not_external_provider:<source>` | Real-provider rollout did not resolve to external provider |
| Blocker | `preview_route_enabled_for_launch_mode:limited_rollout` | Preview is on in canonical limited rollout |
| Blocker | `chrome_extension_origin_not_pinned:<state>` | Extension origin missing or default/dev |
| Blocker | `web_app_origin_not_pinned:<state>` | Web origin missing or default/dev |
| Blocker | `beta_keys_not_safe:<state>` | Beta key missing or default/dev |
| Blocker | `release_fingerprint_mismatch:<field>:<staging>-><production>` | Approved staging build differs from production runtime |
| Warning | `staging_runtime_snapshot_missing` | Approved staging runtime snapshot not present |
| Warning | `production_runtime_snapshot_missing` | Production runtime snapshot not present |
| Warning | `staging_runtime_snapshot_schema_incomplete` | Staging snapshot file exists but does not expose the required parity fields |
| Warning | `production_runtime_snapshot_schema_incomplete` | Production snapshot file exists but does not expose the required parity fields |
| Warning | `runtime_parity_evaluated_from_local_env_only` | Checker had to fall back to local repo env |
| Warning | `release_fingerprint_unavailable` | Provenance fields were not sufficient to verify parity |
| Warning | `artifact_age_exceeds_recommended_window:<artifact>` | Artifact is older than the 48h recommended window |
| Warning | `web_rate_limit_default_drift_unpinned` | Runtime is still relying on middleware default rate limiting |
| Warning | `app_env_not_prod_like:<env>` | Runtime is not staging/prod-like |

## How To Read The Outcome

- blockers mean limited rollout is not ready
- warnings mean operator review is required, but non-blocking warnings do not automatically fail launch readiness
- missing, stale, or schema-incomplete runtime snapshots mean deployed-env parity is not yet verified, even if repo-side readiness is green
- the final limited-rollout judgment comes from `reports/launch/latest.json` and `reports/launch/latest.md` after running `./.venv/bin/python scripts/launch_check.py --from-artifacts`

## Required Artifact Review

Operators should inspect:

- `hub-api/reports/launch/preflight.json`
- `hub-api/reports/launch/preflight.md`
- `hub-api/reports/launch/latest.json`
- `hub-api/reports/launch/latest.md`
- `hub-api/reports/external_provider/latest.json`
- `hub-api/reports/provider_stub/latest.json`
- `hub-api/debug_runs/launch_ops/external_provider/verification/summary.json`
- `hub-api/debug_runs/launch_ops/provider_shim/staging_compare/summary.json`
- `hub-api/reports/launch/runtime_snapshots/staging.json`
- `hub-api/reports/launch/runtime_snapshots/production.json`

The markdown report now includes:

- release fingerprint parity
- resolved runtime path
- preview route invariant
- artifact freshness and provenance
- origin and beta-key safety

## Final Judgment Rule

Limited rollout is ready only when:

- staging artifacts are fresh and green
- production runtime snapshot is present and fresh
- production runtime resolves the same approved release fingerprint as staging
- production runtime resolves `effective_provider_source=external_provider`
- preview remains off
- origins and beta keys are pinned and non-dev
- `config_blockers=[]`

If runtime snapshots are missing, the checker may still say repo-side launch parity is complete. That does not mean deployed-env readiness is complete.
