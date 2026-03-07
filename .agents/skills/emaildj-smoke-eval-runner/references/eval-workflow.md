# EmailDJ Eval Workflow

## Existing entrypoints

Work from `backend/`.

- `python -m evals.eval_run --payloads <selector> --stages <selector> --report <path>`
- `python -m evals.debug_stage --stage a --payload <payload_id> --raw`

Current stage selectors for `eval_run.py`:

- `all`
- `a`
- `b`
- `b0`
- `c0`
- `c`
- `d`
- `e`

`debug_stage.py` currently supports only stage `a`.

## Report reading

Useful top-level report fields:

- `payload_results`
- `stage_pass_rates`
- `overall_pass_rate`
- `hard_fail_rate`
- `failure_taxonomy`

Useful per-payload fields:

- `pipeline_ok`
- `pipeline_error`
- `judge_results`
- `hard_fail_triggered`
- `hard_fail_criteria`
- `trace_id`

## Root-cause buckets

Use these buckets when summarizing a report:

- `bad_brief`: stage `CONTEXT_SYNTHESIS`
- `bad_fit_or_angle`: stage `FIT_REASONING`, `ANGLE_PICKER`, or `ONE_LINER_COMPRESSOR`
- `bad_generation`: stage `EMAIL_GENERATION` or `EMAIL_REWRITE`
- `bad_validation`: stage `EMAIL_QA`
- `provider_or_transport`: provider unavailable, timeout, DNS, or transport setup issues

## Replay guidance

- For stage A failures, prefer `python -m evals.debug_stage --stage a --payload <payload_id> --raw`
- For later-stage failures, prefer `python -m evals.eval_run --payloads <payload_id> --stages <selector> --raw --fail-fast`
- Use the trace ID from the report to inspect `backend/debug_traces/**`
