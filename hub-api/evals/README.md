# Lock Compliance Scorecard

## Commands

Run from `hub-api/`:

- `./scripts/eval:smoke`
- `./scripts/eval:full`
- `./scripts/eval:focus --tag offer_binding`
- `./scripts/eval:full --real` (requires provider keys)

## Output artifacts

Every run writes:

- `reports/latest.json`
- `reports/latest.md`
- Timestamped copies under `reports/history/`

## Dataset

- Full gold set: `evals/gold_set.full.json` (96 cases)
- Smoke IDs: `evals/gold_set.smoke_ids.json` (10 cases)
- Schema: `evals/gold_set.schema.json`

## Violation codes

- `GREET_FULL_NAME`
- `GREET_MISSING`
- `OFFER_MISSING`
- `OFFER_DRIFT`
- `CTA_MISMATCH`
- `CTA_NOT_FINAL`
- `FORBIDDEN_OTHER_PRODUCT`
- `RESEARCH_INJECTION_FOLLOWED`
- `INTERNAL_LEAKAGE`
- `UNSUPPORTED_OBJECTIVE_CLAIM`
