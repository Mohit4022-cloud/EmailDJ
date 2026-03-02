# Lock Compliance Scorecard

## Commands

Run from `hub-api/`:

- `./scripts/eval:smoke`
- `./scripts/eval:full`
- `./scripts/eval:focus --tag offer_binding`
- `./scripts/eval:parity` (preview/generate parity gate)
- `./scripts/eval:adversarial` (dedicated injection/leakage red-team pack)
- `./scripts/eval:full --real` (requires provider keys)
- `./scripts/eval:judge:smoke` (5-case quality judge smoke)
- `./scripts/eval:judge:full` (96-case quality judge run + calibration)
- `./scripts/eval:judge:pairwise --a-report reports/baseline.json --b-report reports/latest.json`

## Output artifacts

Every run writes:

- `reports/latest.json`
- `reports/latest.md`
- Timestamped copies under `reports/history/`
- Judge cache/artifacts under `reports/judge/`

## Dataset

- Full gold set: `evals/gold_set.full.json` (96 cases)
- Smoke IDs: `evals/gold_set.smoke_ids.json` (10 cases)
- Parity IDs: `evals/parity_ids.json` (12 mixed cases)
- Adversarial pack: `evals/gold_set.adversarial.json` (18 cases)
- Judge calibration set: `evals/judge/calibration_set.v1.json` (20 labeled examples)
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
