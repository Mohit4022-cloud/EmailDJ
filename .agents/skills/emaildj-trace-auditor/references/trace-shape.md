# EmailDJ Trace Shape

## Summary trace

Summary traces live at `backend/debug_traces/<date>/<trace_id>.json`.

Use these fields first:

- `outcome`: final pipeline status, failure code, and failing stage
- `stage_stats`: ordered stage events; the last event for a stage is the effective status
- `validation_errors`: validator codes already surfaced by the orchestrator
- `meta`: preset, sliders, research state, cache state when available
- `hashes.request:normalized`: best grouping key for comparing preset behavior on the same request

## Raw trace

Raw traces live at `backend/debug_traces/<date>/_raw/<trace_id>.json`.

Use these fields when the summary is not enough:

- `stage_payloads[*].stage`
- `stage_payloads[*].status`
- `stage_payloads[*].output`: completed artifact, or sometimes a failed artifact that is still useful
- `stage_payloads[*].artifact_status`
- `stage_payloads[*].error_code`
- `stage_payloads[*].details.codes`

Common raw artifact shapes:

- `CONTEXT_SYNTHESIS`: `MessagingBrief`
- `FIT_REASONING`: `FitMap`
- `ANGLE_PICKER`: `AngleSet`
- `ONE_LINER_COMPRESSOR`: `MessageAtoms` or an equivalent line-based atom artifact with `opener_line`, `value_line`, `proof_line`, and `cta_line`
- `EMAIL_GENERATION` and `EMAIL_REWRITE`: `EmailDraft`
- `EMAIL_QA`: `QAReport`

## Classification clues

Use these evidence patterns:

- `transport_or_provider`: `OPENAI_UNAVAILABLE`, DNS errors, timeout text, provider unavailable text
- `fallback_leakage`: any `fallback` signal in error text, outcome text, or draft source path
- `cta_drift`: `cta_not_final_line`, `duplicate_cta_line`, or explicit CTA mismatch text
- `repetition_or_copy_qa`: `repetition_detected`, banned phrase issues, generic opener issues, ungrounded personalization, template leakage
- `missing_artifact`: `artifact_missing`, report-only missing artifacts, or stage judge failures that only say artifact missing
- `validator_failure`: validator codes are present and none of the stronger buckets above fit better
- `schema_contract`: JSON decode or schema mismatch without validator-code evidence

## Related files

- `backend/app/engine/tracer.py`
- `backend/evals/eval_run.py`
- `backend/evals/stage_judge.py`
- `backend/app/engine/validators.py`
