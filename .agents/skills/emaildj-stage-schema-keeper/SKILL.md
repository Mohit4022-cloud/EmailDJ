---
name: emaildj-stage-schema-keeper
description: Guard EmailDJ staged JSON contracts and keep prompts, response schemas, validators, judges, and downstream consumers aligned. Use when a stage output such as `MessagingBrief`, `FitMap`, `AngleSet`, `MessageAtoms`, `EmailDraft`, or `QAReport` fails schema validation, breaks cross-stage IDs, or drifts from the prompt or validator expectations.
---

# EmailDJ Stage Schema Keeper

## Overview

Repair stage contract issues without weakening the pipeline. Use the stage map reference to find the exact prompt, schema constant, validator or normalizer, and tests that must move together.

## Repair Workflow

1. Identify the failing stage name and artifact name from the trace or eval report.
2. Open `references/stage-map.md` and jump to the matching stage row.
3. Inspect the prompt module, schema definition in `backend/app/engine/schemas.py`, validator or normalizer in `backend/app/engine/validators.py`, and the downstream consumer before editing.
4. Change the contract in one pass:
   - prompt instructions
   - response schema
   - validator or normalizer
   - consumer or adapter code
   - stage judge or eval expectations
   - targeted tests
5. Preserve fail-closed behavior. Do not loosen a validator or judge just to let a bad artifact through.

## Contract Rules

- Keep stage names consistent between prompt files, trace output, evals, and explanations.
- Keep cross-stage identifiers stable: hook IDs, fit hypothesis IDs, angle IDs, selected angle IDs, used hook IDs, and locked CTA fields.
- Treat `EMAIL_QA` specially: it uses normalization plus rewrite planning rather than a dedicated strict validator function.
- When adding or removing fields, update tests in the same change. Schema drift without test coverage is not acceptable in this repo.

## Commands

```bash
rg -n "RF_EMAIL_DRAFT|validate_email_draft|normalize_qa_report" backend/app/engine
pytest backend/tests/test_stage_a_validator.py -q
pytest backend/tests/test_stage_runner.py -q
```

## References

- Read `references/stage-map.md` before editing a stage contract. It is the quickest way to find the prompt, schema, validator, eval selector, and likely tests.
