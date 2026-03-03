# ADR-0001: Lock Enforcement Model (offer_lock + cta_lock)

- Status: Accepted
- Date: 2026-03-02
- Owners: AI Safety, Backend
- Related code paths: `hub-api/email_generation/output_enforcement.py`, `hub-api/email_generation/compliance_rules.py`, `hub-api/email_generation/runtime_policies.py`
- Related docs: `docs/policy/control_contract.md`, `docs/contracts/streaming_sse.md`

## Context

EmailDJ generates outbound sales emails for B2B SDRs. Without hard constraints, LLMs
routinely hallucinate product claims, introduce off-script CTAs, and drift from the
intended pitch. Prompt-level instructions alone ("only pitch X") are insufficient: models
ignore or misinterpret them under pressure from research text, conversation history, or
model drift after updates.

Two invariants are non-negotiable for the product to be trustworthy:
1. **offer_lock** — the email may pitch exactly one product/offering, specified by the caller.
2. **cta_lock** — the email must contain the caller's exact CTA text, exactly once, as the
   only call to action.

## Decision

Enforce both locks **at the output layer**, not the prompt layer. The system:
1. Generates a draft (any model, any provider).
2. Validates the draft against a deterministic rule set (`validate_ctco_output`).
3. If violations are found, applies one of three enforcement levels based on runtime config:
   - `warn` — return draft with violation metadata attached.
   - `repair` — re-generate with violation context injected into the next prompt (repair loop).
   - `block` — hard-fail and return an error.
4. Exposes all violation codes, retry counts, and enforcement level in the SSE `done` event
   so every generation is auditable without inspecting logs.

## Rationale

- **Output-layer enforcement survives model changes.** If we change providers or model
  versions, the validation rules remain stable and will catch regressions automatically.
- **Deterministic rules are testable.** Regex and structural checks are unit-testable with
  zero LLM calls (`hub-api/tests/test_ctco_validation.py`).
- **Repair loop preserves flow.** Rather than hard-blocking on the first violation, the
  repair loop gives the LLM one more attempt with explicit correction guidance. This
  reduces user-visible errors while keeping the invariant enforced.
- **Observability first.** Every SSE `done` payload includes `violation_codes`,
  `violation_count`, `repaired`, `repair_attempt_count`, and `enforcement_level`. Operators
  can monitor compliance without tailing logs.

## Alternatives Considered

1. **Prompt-only enforcement** — instruct the model to follow locks. Rejected: models
   ignore instructions under adversarial research text; no auditability; breaks silently
   after model upgrades.
2. **Post-generation filter (strip offending content)** — strip forbidden phrases rather
   than regenerate. Rejected: produces grammatically broken output; doesn't fix structural
   violations (missing offer, multiple CTAs).
3. **Separate validation microservice** — run a dedicated validator model. Rejected: adds
   latency, infra cost, and a second model's own reliability surface; deterministic rules
   are faster and more reliable for this category of checks.

## Consequences

- Positive: Lock correctness is measurable, regression-testable, and auditable per-request.
- Positive: Works across any LLM provider in the cascade.
- Negative: Repair loop adds latency (one extra generation round-trip) when violations occur.
- Negative: `block` mode can surface hard errors to users; must be used intentionally.
- Risk mitigation: `EMAILDJ_REPAIR_LOOP_ENABLED` and `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL`
  allow runtime tuning without code changes. Default is `repair` — the least-disruptive mode.

## Rollout / Verification

- Required config: `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL=repair`, `EMAILDJ_REPAIR_LOOP_ENABLED=1`
- Required tests: `hub-api/tests/test_ctco_validation.py`, `hub-api/tests/test_output_enforcement.py`
- CI gate: adversarial eval suite (`hub-api/scripts/eval:adversarial`) validates lock
  correctness against known-violation inputs on every nightly run.
- Observability: monitor `violation_count > 0` in SSE done events; alert on sustained
  repair rates above baseline.

## Follow-up

- [ ] Add violation rate dashboard in `docs/ops/runbooks.md` (ops team).
- [ ] Consider graduated repair budget (max N attempts configurable per preset).
- [ ] Document per-preset lock overrides if/when introduced.
