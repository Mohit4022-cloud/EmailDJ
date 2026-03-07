---
name: emaildj-smoke-eval-runner
description: Run or interpret the EmailDJ smoke and judge eval harness and summarize failures by root cause. Use when working with `backend/evals/eval_run.py`, `backend/evals/debug_stage.py`, report JSON in `backend/evals/reports`, or when Codex needs to separate bad brief generation from bad fit or angle logic, bad generation, bad validation, or provider and transport failures.
---

# EmailDJ Smoke Eval Runner

## Overview

Use the existing repo eval harness instead of inventing a new one. Run focused evals by payload and stage selector, then use the bundled summarizer to collapse report JSON into buckets that are useful for debugging.

## Workflow

1. Work from `backend/` with the repo's normal environment loaded.
2. Run the existing harness:
   - `python -m evals.eval_run --payloads <selector> --stages <selector> --report <path>`
   - `python -m evals.debug_stage --stage a --payload <payload_id> --raw` for the current stage-A deep debug flow
3. Summarize the resulting report with `python .agents/skills/emaildj-smoke-eval-runner/scripts/summarize_eval_report.py <report-path>`.
4. Route the result:
   - `bad_brief`: use `$emaildj-stage-schema-keeper`
   - `bad_fit_or_angle`: inspect stages `b`, `b0`, or `c0`
   - `bad_generation` or `bad_validation`: inspect stages `c`, `d`, or `e`
   - `provider_or_transport`: fix the environment before changing prompts or validators

## Eval Rules

- Prefer narrow replays before broad sweeps. Use a single payload and a single stage selector when investigating a concrete failure.
- Keep report files in `backend/evals/reports/`.
- Use `--raw` when you need stage artifacts in `backend/debug_traces/`.
- Do not treat provider failures as prompt regressions.

## Commands

```bash
cd backend
python -m evals.eval_run --payloads high_signal --stages all --report evals/reports/high_signal_smoke.json
python -m evals.debug_stage --stage a --payload high_signal_01 --raw
python ../.agents/skills/emaildj-smoke-eval-runner/scripts/summarize_eval_report.py evals/reports/high_signal_smoke.json
```

## References

- Read `references/eval-workflow.md` for the stage selectors, bucket meanings, and replay guidance.
