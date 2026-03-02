# LLM Judge Eval Runbook

## Commands

Run from `hub-api/`:

- `./scripts/eval:smoke`
- `./scripts/eval:judge:smoke`
- `./scripts/eval:judge:full`
- `./scripts/eval:judge:pairwise --a-report <baseline.json> --b-report <candidate.json>`
- `./scripts/eval:judge:sanity`
- `./scripts/eval:judge:stability`
- `./scripts/eval:judge:calibrate`
- `./scripts/eval:judge:regression-gate --baseline-report <...> --candidate-report <...> --pairwise-report <...>`

## Hard Gate Rule

Lock compliance remains the hard gate. Any lock failure skips judge scoring for that case.

## Key Thresholds

- Lock compliance must remain `100%`.
- Judge `overall >= 3.8`.
- Judge `credibility_no_overclaim >= 5.0`.

Thresholds are calibrated from `evals/judge/calibration_set.v1.json` using `eval:judge:calibrate`.

## Determinism + Cache Verification

Run:

- `./scripts/eval:judge:stability`

Expected outcomes:

- Same settings run twice -> identical aggregate and per-case scores.
- Second run -> mostly/all cache hits.
- Rubric version bump or model bump -> cache misses/recompute as expected.
- Fixed pairwise seed -> deterministic A/B order plan.

## Sentinel Drift Suite

Run:

- `./scripts/eval:judge:sanity`

Coverage:

- 2 excellent, 2 average, 2 generic/bad, 2 policy-bad, 2 lock-edge cases.
- Lock-edge cases must fail hard gate and be skipped by judge.

## Actionable Feedback Tags

- `HOOK_TOO_GENERIC` -> require one specific research fact in opening hook.
- `CREDIBILITY_OVERCLAIM` -> hedge claims and remove unsupported numbers.
- `CTA_WEAK` -> switch to explicit low-friction CTA template.
- `TONE_MISMATCH` -> adjust tone instructions/sliders to professional-neutral.

## Prompt Regression Gate

For prompt contract changes:

1. Generate baseline: `./scripts/eval:judge:full` on main.
2. Generate candidate: `./scripts/eval:judge:full` on PR.
3. Run pairwise: `./scripts/eval:judge:pairwise --a-report <baseline> --b-report <candidate>`.
4. Gate:
   - `./scripts/eval:judge:regression-gate --baseline-report <baseline> --candidate-report <candidate> --pairwise-report <pairwise>`
   - Candidate must not regress relevance or credibility means.

## If Judge Score Drops But Locks Pass

1. Re-run `./scripts/eval:judge:full` with cache warm and then with cache bypass (`rm -rf reports/judge/cache`).
2. Compare `reports/latest.json` against previous baseline for criteria deltas.
3. Run pairwise comparison against baseline outputs.
4. Review top recurring quality flags and per-case rationale bullets.
5. Verify calibration agreement metrics from the `judge.summary` section.
6. If disagreement rises or drift is suspected, refresh the calibration labels before gating prompt changes.
