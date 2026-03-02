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
- `./scripts/eval:judge:trend`
- `./scripts/eval:judge:drift-guard`
- `./scripts/eval:judge:real-corpus`

## Hard Gate Rule

Lock compliance remains the hard gate. Any lock failure skips judge scoring for that case.

## Key Thresholds

- Lock compliance must remain `100%`.
- Judge `overall >= 3.8`.
- Judge `credibility_no_overclaim >= 4.0`.
- Binary overclaim check hard-fail: `auto_fail_overclaim_present`.

Thresholds are calibrated from `evals/judge/calibration_set.v2.json` using `eval:judge:calibrate`.

Every judge report header includes:

- `judge_model`
- `judge_model_version`
- `judge_mode`

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

- `OVERCLAIM_REWRITE` -> rewrite claims to hedged language, remove numbers, avoid guarantees.
- `FILLER_COMPRESSION` -> compress body by 20%, remove generic openers, require one concrete hook.
- `CLARITY_STRUCTURE` -> enforce one-sentence opener + two bullets + one final CTA.
- `HOOK_TOO_GENERIC` -> require one specific research fact in opening hook.
- `CTA_WEAK` -> switch to explicit low-friction CTA template.
- `TONE_MISMATCH` -> adjust tone instructions/sliders to professional-neutral.

Nightly report footer includes `Recommended Next Prompt Adjustments` with 2-3 concrete actions derived deterministically from top binary/flag signals.

## Trend Triage (under 60 seconds)

Open `reports/judge/trend/latest.md` and read in order:

1. `What Got Worse` delta table (overall/relevance/credibility/overclaim/pass-rate).
2. `Top 5 Rising Failure Flags` (filler/clarity signals).
3. `Most Regressed 10 Cases` (IDs + snippets + rationale).

This is the fastest path to answer "what regressed?".

## Judge Drift Protection

Nightly drift guard compares current calibration metadata vs previous nightly metadata artifact.

- If `judge_model` or `judge_model_version` changed:
  - calibration still runs
  - threshold deltas are computed and written to `reports/judge/drift_guard/latest.json`
  - gate is blocked unless `workflow_dispatch` is run with `allow_judge_drift_override=true`

No silent threshold drift is allowed.

## CI Artifacts

Nightly uploads:

- `judge-nightly-reports` (latest eval/trend/calibration/real-corpus/drift reports)
- `judge-nightly-metadata` (`nightly_metadata.json`)

Fetch artifacts:

- `gh run list --workflow ci.yml --limit 5`
- `gh run download <run-id> -n judge-nightly-reports -D /tmp/judge-nightly`
- `gh run download <run-id> -n judge-nightly-metadata -D /tmp/judge-nightly-meta`

## Real Corpus

Dataset path: `evals/judge/real_corpus.v1.json`

Minimum workflow:

1. Collect 100-300 anonymized outputs.
2. Label at least 50-100 with `quality` (`good|ok|bad`) and `overclaim_present` (`true|false`).
3. Run nightly `./scripts/eval:judge:real-corpus`.

## Prompt Regression Gate

For prompt contract changes:

1. Generate baseline: `./scripts/eval:judge:full` on main.
2. Generate candidate: `./scripts/eval:judge:full` on PR.
3. Run pairwise: `./scripts/eval:judge:pairwise --a-report <baseline> --b-report <candidate>`.
4. Gate:
   - `./scripts/eval:judge:regression-gate --baseline-report <baseline> --candidate-report <candidate> --pairwise-report <pairwise>`
   - Candidate budgets:
     - overall mean must not drop by more than `0.05`
     - relevance mean must not drop by more than `0.05`
     - credibility mean must not drop at all
     - pass rate must not decrease

## If Judge Score Drops But Locks Pass

1. Re-run `./scripts/eval:judge:full` with cache warm and then with cache bypass (`rm -rf reports/judge/cache`).
2. Compare `reports/latest.json` against previous baseline for criteria deltas.
3. Run pairwise comparison against baseline outputs.
4. Review top recurring quality flags and per-case rationale bullets.
5. Verify calibration agreement metrics from the `judge.summary` section.
6. If disagreement rises or drift is suspected, refresh the calibration labels before gating prompt changes.
