# Lock Compliance Runbook

## Scope

Operational guide for web generation (`/web/v1/generate`, `/web/v1/stream/{id}`) and preset preview batch (`/web/v1/preset-previews/batch`).

## Fast Triage

1. Check runtime mode/provider attestation in Hub API startup logs (`generation_runtime_attestation`).
2. Check stream `done` metadata for `mode`, `provider`, `model`, `provider_attempt_count`, `validator_attempt_count`, `json_repair_count`, `violation_retry_count`, `repaired`.
3. Check stream/preview debug bundle for `request_id`, `session_id`, `violation_codes`, `violation_count`, `enforcement_level`, `repair_loop_enabled`.
4. Check preview batch `meta` for `generation_mode`, `provider`, `model`, `repair_attempt_count`, `initial_violation_count`, `final_violation_count`.
5. Check compliance dashboard: `GET /web/v1/compliance/dashboard?days=1`.

## If X Then Y

### 1) Startup fails in real mode

- Symptom: Hub API fails with missing provider key error.
- Action:
  - For `EMAILDJ_REAL_PROVIDER=openai`, set `OPENAI_API_KEY`.
  - For `EMAILDJ_REAL_PROVIDER=anthropic`, set `ANTHROPIC_API_KEY`.
  - For `EMAILDJ_REAL_PROVIDER=groq`, set `GROQ_API_KEY`.
  - If preview pipeline is enabled in real mode, set `OPENAI_API_KEY`.
- Verify: restart Hub API and confirm `generation_runtime_attestation` log appears.

### 2) UI says mock unexpectedly

- Symptom: mode badge displays `MOCK MODE`.
- Action:
  - Confirm runtime env `EMAILDJ_QUICK_GENERATE_MODE=real`.
  - Confirm deployment secret/env injection is active for Hub API process.
  - Restart process and verify startup attestation reflects `real`.
- Verify: new generation stream `done` event reports `mode=real`.

### 3) Repairs spike or retries spike

- Symptom: `repaired=true` frequently, or high `validator_attempt_count`.
- Action:
  - Pull latest compliance dashboard counts.
  - Run targeted eval: `./scripts/eval:focus --tag offer_binding`.
  - Inspect recurring violation codes in `reports/latest.md` and logs.
  - Sample successful requests via `EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE` (default `0.01`), failures are always fully logged.
  - Roll back recent prompt/preset/UI changes if the same codes spike.
- Verify: rerun `./scripts/eval:smoke` and check repairs decline in logs.

### 4) Preview and generate behavior drift

- Symptom: preview passes but generated draft violates lock/CTA expectations (or vice versa).
- Action:
  - Run parity gate: `./scripts/eval:parity`.
  - Run lock harness smoke: `./scripts/eval:smoke`.
  - Block release if parity gate fails.
- Verify: both commands return 0.

### 5) Lock violations in production

- Symptom: dashboard shows rising `offer_lock_missing`/`cta_lock_not_used_exactly_once`.
- Action:
  - Confirm no fallback path is active in UI (preview must use batch route only).
  - Inspect latest logs for violation codes and retry counts.
  - Use runtime toggles as emergency brake:
    - `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL=warn|repair|block`
    - `EMAILDJ_REPAIR_LOOP_ENABLED=0|1`
  - If required, temporarily force `EMAILDJ_QUICK_GENERATE_MODE=mock` to stabilize while investigating.
- Verify: dashboard counts stabilize and smoke/parity gates pass.

## Release Gate Commands

Run from `/Users/mohit/EmailDJ/hub-api`:

- `./scripts/eval:smoke`
- `./scripts/eval:parity`
- `./scripts/eval:adversarial`
- `./scripts/eval:full` (pre-release or nightly)
- `pytest -q tests/integration/test_web_mvp_api.py tests/test_preset_preview_pipeline.py`
- `./scripts/checks.sh`
