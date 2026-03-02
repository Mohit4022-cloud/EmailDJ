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
- `./scripts/eval:judge:sanity` (10 sentinel judge drift/gaming checks)
- `./scripts/eval:judge:stability` (determinism + cache correctness verification)
- `./scripts/eval:judge:calibrate` (threshold sweep on calibration labels)
- `./scripts/eval:judge:regression-gate --baseline-report <...> --candidate-report <...>`
- `./scripts/eval:judge:trend` (nightly quality trend deltas from artifact history)
- `./scripts/eval:judge:drift-guard` (blocks gating if judge model/version drifts without override)
- `./scripts/eval:judge:real-corpus` (judge evaluation on anonymized real-world corpus)

## Output artifacts

Every run writes:

- `reports/latest.json`
- `reports/latest.md`
- Timestamped copies under `reports/history/`
- Judge cache/artifacts under `reports/judge/`
  - Commit-scoped artifacts: `reports/judge/artifacts/<candidate_id>/`

## Dataset

- Full gold set: `evals/gold_set.full.json` (96 cases)
- Smoke IDs: `evals/gold_set.smoke_ids.json` (10 cases)
- Parity IDs: `evals/parity_ids.json` (12 mixed cases)
- Adversarial pack: `evals/gold_set.adversarial.json` (18 cases)
- Judge calibration set: `evals/judge/calibration_set.v2.json` (60 labeled examples)
- Judge sentinel suite: `evals/judge/sentinel_cases.v1.json` (10 drift checks)
- Real anonymized corpus: `evals/judge/real_corpus.v1.json`
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
