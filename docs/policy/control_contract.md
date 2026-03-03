# Control Contract (Non-Negotiable)

This policy defines output invariants that generation must satisfy. It is enforced in code, not just prompt text.

Primary enforcement source:
- `hub-api/email_generation/remix_engine.py::validate_ctco_output`

## Invariants
1. Offer lock only
- Rule: output can pitch only `offer_lock`.
- Enforcement: `offer_lock_missing`, `offer_lock_body_verbatim_missing`, `forbidden_other_product_mentioned:*`.

2. CTA lock exactness
- Rule: use exact `cta_lock_effective` exactly once, as the only CTA.
- Enforcement: `cta_lock_not_used_exactly_once`, `cta_near_match_detected`, `additional_cta_detected`.

3. Greeting normalization
- Rule: greet by first name only.
- Enforcement: `greeting_missing_or_invalid`, `greeting_first_name_mismatch`, `greeting_not_first_name_only`.

4. Internal leakage ban
- Rule: no internal tool/prompting terms in customer-facing text.
- Enforcement: `internal_leakage_term:*` using `_NO_LEAKAGE_TERMS`.

5. Claims policy
- Rule: quantified/performance claims must be grounded in approved research text.
- Enforcement: `unsubstantiated_statistical_claim`, `unsubstantiated_performance_claim`, `unsubstantiated_claim:*`.

6. Cash-equivalent CTA ban
- Rule: no gift cards/cash incentive CTA.
- Enforcement: `cash_equivalent_cta_detected`.

7. Length bands
- Rule: body length must remain in slider-defined word band.
- Enforcement: `length_out_of_range:{actual}_expected_{min}_{max}`.

8. Prospect grounding
- Rule: body must reference prospect identity markers.
- Enforcement: `prospect_reference_missing`.

## Enforcement Levels
Configured by `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL` in:
- `hub-api/email_generation/runtime_policies.py`

Modes:
- `warn`: return output with violations metadata
- `repair`: retry + repair loop, fail if unresolved
- `block`: fail immediately on violations

Repair loop toggle:
- `EMAILDJ_REPAIR_LOOP_ENABLED`.

## Startup Policy Guards
Runtime env requirements enforced at startup in:
- `hub-api/main.py::_validate_env`

Examples:
- invalid mode/provider rejected
- real mode requires provider key
- preview pipeline in real mode requires `OPENAI_API_KEY`

## Preview Pipeline Contract Alignment
Preset preview path enforces equivalent constraints in:
- `hub-api/email_generation/preset_preview_pipeline.py::_violation_messages`

## Why This Exists
The product intent is controlled personalization, not free-form generation. Hard validation + repair keeps lock correctness measurable and regression-testable under model drift.
