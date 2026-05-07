# Operations Runbooks

Runbooks for known failure modes. Each entry: symptoms → diagnosis → remediation → prevention.

Launch command and artifact reference:
- [`docs/ops/launch_operator.md`](/Users/mohit/EmailDJ/docs/ops/launch_operator.md)

---

## RB-01: LLM Provider Outage / All Tiers Failing

**Symptoms**
- SSE streams emit `error` events with provider failure messages.
- `provider_attempt_count` > 1 in `done` metadata.
- Slack alert from `infra/alerting.py` (QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD breached).

**Diagnosis**
1. Check `LOG_LEVEL=DEBUG` logs for cascade failure trace.
2. Check provider status pages (OpenAI, Anthropic, Groq).
3. Check `EMAILDJ_REAL_PROVIDER` env — is the preferred provider down?

**Remediation**
1. If preferred provider is down, switch `EMAILDJ_REAL_PROVIDER` to a healthy provider (no code deploy needed).
2. If all real providers down, switch `EMAILDJ_QUICK_GENERATE_MODE=mock` to unblock users with mock output (clearly communicate this is mock).
3. Restart Hub API after env change.

**Prevention**
- Model cascade (Tier 1→2→3) provides automatic fallback.
- Monitor `provider_attempt_count > 1` rate as a leading indicator.

---

## RB-02: Redis Unavailable

**Symptoms**
- App fails to start: `get_redis().ping()` raises connection error.
- Context vault misses on every request.
- Session-based remix fails.

**Diagnosis**
1. Check `REDIS_URL` in `.env`.
2. Ping Redis directly: `redis-cli -u $REDIS_URL ping`.

**Remediation**
1. Restore Redis instance.
2. For CI/test environments: set `REDIS_FORCE_INMEMORY=1` to use in-memory shim.
3. For production: context vault will miss on every request until Redis is restored.
   Generation still works (vault miss → no enrichment).

**Prevention**
- Redis is required for session continuity and context vault. Use a managed Redis with
  replication (e.g. Redis Cloud, ElastiCache) in production.
- Launch modes are stricter than CI/test: `REDIS_FORCE_INMEMORY=1` is blocked by
  launch checks and reported as `redis_not_durable_for_launch_mode`.

---

## RB-03: Repair Loop Causing Latency Spikes

**Symptoms**
- P95 latency significantly elevated.
- `repair_attempt_count > 0` in done metadata on many requests.
- `violation_codes` frequently contain the same violation type.

**Diagnosis**
1. Inspect `violation_codes` distribution to identify which rule is firing most.
2. Check if a recent model update or prompt change introduced a new failure mode.
3. Check if `offer_lock` or `cta_lock` values are unusually long/complex.

**Remediation**
1. If a specific violation type is a false positive: investigate the detection pattern in
   `compliance_rules.py` — do NOT loosen rules without an ADR.
2. If a model update broke compliance: revert `EMAILDJ_REAL_PROVIDER` to a known-good model.
3. Temporary: set `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL=warn` to surface violations without
   blocking (accept degraded compliance, communicate to team).

**Prevention**
- Run adversarial eval suite (`scripts/eval:adversarial`) before any model or prompt change.
- Monitor `repair_attempt_count` and `violation_count` as SLIs.

---

## RB-04: Mode Misconfiguration (mock vs real)

**Symptoms**
- Generation output is clearly template/stub text, not personalized.
- `mode: mock` in SSE done metadata when `real` was expected.

**Diagnosis**
1. Check `EMAILDJ_QUICK_GENERATE_MODE` in environment.
2. Check startup log: `generation_runtime_attestation` log line shows `quick_generate_mode`.

**Remediation**
1. Set `EMAILDJ_QUICK_GENERATE_MODE=real`.
2. Ensure the correct provider API key is set for `EMAILDJ_REAL_PROVIDER`.
3. Restart Hub API.

For `limited_rollout` and `broad_launch`, `USE_PROVIDER_STUB=1` and missing
provider credentials are startup/launch blockers. A launch-ready runtime report
must show `effective_provider_source=external_provider`.

## RB-05: Cost Guard Blocking Requests

**Symptoms**
- HTTP 429 responses from Hub API with cost-related error message.
- `CostGuardMiddleware` blocking before generation reaches routers.

**Diagnosis**
1. Check `MONTHLY_COST_CEILING` and current spend tracking.
2. Check `MONTHLY_COST_THROTTLE_MULTIPLIER` — is throttle kicking in early?

**Remediation**
1. Raise `MONTHLY_COST_CEILING` (requires env change + restart).
2. Switch to mock mode if real spend needs to stop immediately.
3. Investigate why spend is elevated — check for runaway retries or large batch jobs.

---

## RB-06: Preset Preview Pipeline Errors

**Symptoms**
- `POST /web/v1/preset-previews/batch` returns 500 or empty previews.
- `EMAILDJ_PRESET_PREVIEW_PIPELINE=off` in logs but requests are expected to succeed.

**Diagnosis**
1. Check `EMAILDJ_PRESET_PREVIEW_PIPELINE` — must be `on`.
2. Check `OPENAI_API_KEY` — preview pipeline is OpenAI-backed even when other providers are used.
3. Check preset extractor and generator model settings.

**Remediation**
1. Set `EMAILDJ_PRESET_PREVIEW_PIPELINE=on` and ensure `OPENAI_API_KEY` is set.
2. Restart Hub API.

---

## RB-07: Launch Durable Infra Blocked

**Symptoms**
- `make launch-audit` reports `durable_infra` as blocked.
- Launch report includes `database_not_durable_for_launch_mode`,
  `redis_not_durable_for_launch_mode`, or `vector_store_not_durable_for_launch_mode`.

**Diagnosis**
1. Check deployment Dashboard values for `REDIS_URL`, `DATABASE_URL`, and `VECTOR_STORE_BACKEND`.
2. Confirm `REDIS_FORCE_INMEMORY` is unset or `0`.
3. Confirm runtime snapshots were captured from deployed staging/prod services, not local env.

**Remediation**
1. Provision managed Redis and set `REDIS_URL`.
2. Provision managed Postgres and set `DATABASE_URL`.
3. Set `VECTOR_STORE_BACKEND=pgvector`.
4. Rerun `make launch-verify-deployed`, then `make launch-audit` and `make launch-handoff`.
