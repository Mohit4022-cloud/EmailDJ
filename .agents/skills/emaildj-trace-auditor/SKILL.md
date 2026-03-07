---
name: emaildj-trace-auditor
description: Inspect EmailDJ backend trace artifacts and classify failures by pipeline stage and root cause. Use when working with `backend/debug_traces/**`, trace IDs, `stage_stats`, `validation_errors`, `_raw` stage payloads, or when a generate/remix/eval run failed and Codex needs to explain whether the problem is schema contract drift, validator failure, repetition or copy QA, CTA drift, fallback leakage, missing artifacts, or transport/provider failure.
---

# EmailDJ Trace Auditor

## Overview

Inspect EmailDJ summary and raw trace JSON together. Use the bundled script for first-pass classification, then verify the evidence against the trace shape reference before proposing a code change.

## Workflow

1. Start from a summary trace in `backend/debug_traces/<date>/<trace_id>.json` when possible.
2. Pair it with the sibling raw trace in `backend/debug_traces/<date>/_raw/<trace_id>.json` if that file exists.
3. Run `python .agents/skills/emaildj-trace-auditor/scripts/summarize_trace.py <trace-path>`.
4. Trust failure precedence in this order: `outcome` -> failed `stage_stats` entry -> failed raw `stage_payload` entry.
5. Hand off based on the classification:
   - `schema_contract` or `validator_failure`: use `$emaildj-stage-schema-keeper`
   - `repetition_or_copy_qa` or `cta_drift`: use `$emaildj-copy-qa-reviewer`
   - preset or slider drift across traces: use `$emaildj-preset-regression-hunter`
6. Quote the failing stage name and the exact codes from the trace in the final explanation.

## Classification Rules

- `transport_or_provider`: OpenAI unavailable, DNS/network errors, timeouts, or transport setup failures.
- `fallback_leakage`: any fallback draft path, fallback text leakage, or `deterministic_fallback_disabled` signal in the generation path.
- `cta_drift`: CTA mismatch, duplicate CTA, or non-final CTA line issues.
- `repetition_or_copy_qa`: repetition, banned phrase, generic opener, ungrounded personalization, template leakage, or other final-copy QA drift.
- `missing_artifact`: stage failed without a usable artifact and the trace mostly reports missing artifact signals.
- `validator_failure`: validator codes are present and the failure is not better explained by the buckets above.
- `schema_contract`: JSON/schema parse failure, missing required fields, or cross-stage linkage breakage without validator-code evidence.
- `unknown`: leave only when the trace does not provide enough evidence to justify a stronger claim.

## Commands

```bash
python .agents/skills/emaildj-trace-auditor/scripts/summarize_trace.py backend/debug_traces/20260305/225d7c02-a263-4a67-9bb1-b79909cb87b7.json
python .agents/skills/emaildj-trace-auditor/scripts/summarize_trace.py backend/debug_traces/20260305/_raw/225d7c02-a263-4a67-9bb1-b79909cb87b7.json
```

## References

- Read `references/trace-shape.md` when the trace fields are unfamiliar or when the summary and raw trace disagree.
- Prefer the script output for quick triage, but always verify the final claim against the underlying trace fields before changing code.
