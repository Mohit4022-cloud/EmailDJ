# LLM Judge Eval Runbook

## Commands

Run from `hub-api/`:

- `./scripts/eval:smoke`
- `./scripts/eval:judge:smoke`
- `./scripts/eval:judge:full`
- `./scripts/eval:judge:pairwise --a-report <baseline.json> --b-report <candidate.json>`

## Hard Gate Rule

Lock compliance remains the hard gate. Any lock failure skips judge scoring for that case.

## Key Thresholds

- Lock compliance must remain `100%`.
- Judge `overall >= 3.8`.
- Judge `credibility_no_overclaim >= 4.2`.

## If Judge Score Drops But Locks Pass

1. Re-run `./scripts/eval:judge:full` with cache warm and then with cache bypass (`rm -rf reports/judge/cache`).
2. Compare `reports/latest.json` against previous baseline for criteria deltas.
3. Run pairwise comparison against baseline outputs.
4. Review top recurring quality flags and per-case rationale bullets.
5. Verify calibration agreement metrics from the `judge.summary` section.
6. If disagreement rises or drift is suspected, refresh the calibration labels before gating prompt changes.

