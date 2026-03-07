---
name: emaildj-preset-regression-hunter
description: Compare EmailDJ preset and slider behavior and flag unexpected drift for the same underlying request. Use when reviewing `preset_id` changes, slider runs, batch preset previews, or multiple traces and reports that should keep the same brief, hook logic, proof grounding, and locked CTA while only style, length, or framing changes.
---

# EmailDJ Preset Regression Hunter

## Overview

Check whether presets behave like style modifiers instead of alternate messaging systems. Use the bundled script to group traces by request hash and report whether brief, hooks, angle selection, proof presence, and CTA lock stayed stable.

## Workflow

1. Gather summary traces, raw traces, or eval report JSON that point to the traces you want to compare.
2. Run `python .agents/skills/emaildj-preset-regression-hunter/scripts/compare_presets.py <path> [<path> ...]`.
3. Compare records grouped by the normalized request hash when it exists. Fall back to trace identity only when the request hash is unavailable.
4. Treat `unexpected_drift` as blocking when it changes brief facts, hooks, proof availability, or CTA lock for the same input.
5. Treat `insufficient_comparison` as a signal to gather more traces for the same request before declaring a preset regression.
6. Route copy-quality-only findings to `$emaildj-copy-qa-reviewer`.

## Stability Rules

- Stable across the same request:
  - `MessagingBrief` facts and hooks
  - `used_hook_ids`
  - locked CTA text
  - presence of grounded proof
- Allowed to vary across presets and sliders:
  - tone, formality, framing, assertiveness
  - sentence count and word budget within contract
  - subject wording and body phrasing
- Treat angle drift as suspicious. It may be acceptable, but it requires explanation.

## Commands

```bash
python .agents/skills/emaildj-preset-regression-hunter/scripts/compare_presets.py backend/debug_traces/20260305
python .agents/skills/emaildj-preset-regression-hunter/scripts/compare_presets.py backend/evals/reports/full_real_judge_postfix.json
```

## References

- Read `references/preset-contract.md` before declaring a regression. The repo explicitly allows style variance and explicitly forbids brief, proof, and CTA drift for the same input.
