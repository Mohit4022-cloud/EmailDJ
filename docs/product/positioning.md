# Product Positioning

## What the System Is
EmailDJ is a controlled outbound drafting system for SDR teams.

It combines:
- lock-based message controls (`offer_lock`, `cta_lock`)
- grounded research shaping
- deterministic validation and repair metadata

Source anchors:
- `hub-api/api/routes/web_mvp.py`
- `hub-api/email_generation/remix_engine.py`
- `hub-api/email_generation/preset_preview_pipeline.py`
- `web-app/src/components/SDRPresetLibrary.js`

## What the System Is Not
- Not a generic creative-writing assistant.
- Not an unconstrained mass-mail generator.
- Not a promise engine for ungrounded performance claims.
- Not a hidden prompt orchestration tool exposed in output.

## Core User Value
1. Consistency under scale
- exact lock enforcement reduces rep-to-rep drift.

2. Faster iteration
- slider-based generate/remix with streaming feedback.

3. Operational visibility
- done metadata includes retry/repair/violation counters for debugging and governance.

## Product Guardrails as Product Features
The controls are product behavior, not internal implementation details:
- CTCO invariants (`validate_ctco_output`)
- startup fail-fast env checks (`_validate_env`)
- parity/adversarial eval gates (`hub-api/scripts/eval:*`)

## Success Criteria
- lock correctness stays stable across model/provider changes
- policy violations are diagnosable from request-level metadata
- docs and contracts track code changes with CI enforcement
