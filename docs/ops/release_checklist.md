# Release Checklist

<!-- AUTO-DRAFTED: review before merge -->

Source: `.github/workflows/ci.yml`, `hub-api/scripts/checks.sh`, `docs/judge_eval_runbook.md`,
`docs/lock_compliance_runbook.md`
Last reviewed: 2026-03-02

Every production release must pass all gates in Phase 1. Phases 2–4 follow a staged rollout.

---

## Phase 1 — Pre-Release Gates (must all pass before merge)

### 1.1 CI Checks Job (every PR)

All steps in the `checks` CI job must be green:

| Gate | Command | Pass Criteria |
|---|---|---|
| Surface contract | `python3 scripts/check_surface_contract.py` | Exit 0 -- launch evidence is scoped to `hub-api`, `web-app`, and `chrome-extension`; legacy surfaces are explicit-only |
| Doc freshness | `python3 scripts/docops/check_doc_freshness.py` | Exit 0 — no bound code changed without doc update |
| Generated docs fresh | `python3 scripts/docops/generate_docs.py --check` | Exit 0 — no stale generated docs |
| Web app tests | `npm test && npm run check:syntax` (`web-app`) | Unit tests pass and JS syntax checks cleanly |
| Web app build | `npm run build` (`web-app`) | Vite production build completes |
| Backend compile | `./scripts/checks.sh` (step 1) | No import errors, all modules load |
| pytest suite | `./scripts/checks.sh` (step 2) | All tests pass |
| OpenAPI snapshot | `./scripts/checks.sh` (step 3) | `openapi.json` matches routes |
| Extension build | `npm test` (chrome-extension) | No build errors, unit tests pass |
| Mock e2e smoke | `./scripts/mock_e2e_smoke.py` | Full generate + stream cycle completes in mock mode |
| Judge smoke (mock) | `./scripts/eval:judge:smoke` | All smoke cases pass |
| Judge sanity (mock) | `./scripts/eval:judge:sanity` | Sentinel cases all pass |

### 1.2 Lock Compliance Gate

Run before any merge touching `email_generation/`, `pii/`, or `api/routes/web_mvp.py`:

```bash
# From hub-api/
source .venv/bin/activate

# Smoke (fast, ~30s)
./scripts/eval:smoke

# Parity gate (preview output ≈ generate output)
./scripts/eval:parity

# Adversarial suite
./scripts/eval:adversarial

# Full suite
./scripts/eval:judge:full
```

**Hard gate rules** (any failure blocks release):
- Offer lock present and exact: 100% compliance required
- CTA lock present exactly once: 100% compliance required
- No internal leakage terms: 100% compliance required
- No unsubstantiated absolute revenue/stat claims: 100% compliance required

See `docs/lock_compliance_runbook.md` for triage steps.

### 1.3 Pairwise Regression Gate (prompt/rubric changes only)

Triggered automatically when `hub-api/evals/judge/prompts.py` or
`hub-api/evals/judge/rubric.py` changes. Compares candidate vs baseline using
`./scripts/eval:judge:regression-gate`. Candidate must not regress on any gold-set metric.

---

## Phase 2 — Merge to Main

1. Squash-merge the PR after all Phase 1 gates are green.
2. Verify CI `checks` job passes on main.
3. Confirm doc freshness check passes on the merge commit.

---

## Phase 3 — Staged Rollout

### 3.1 Mock Mode Verification

```bash
# Verify mock mode still works correctly after deploy
EMAILDJ_QUICK_GENERATE_MODE=mock python hub-api/scripts/mock_e2e_smoke.py

# Verify real mode requires credentials (does not silently fall back)
python hub-api/scripts/real_mode_failfast_smoke.py
```

### 3.2 Real Mode Canary

Enable real mode for a single provider and verify against live APIs:

```bash
EMAILDJ_QUICK_GENERATE_MODE=real \
EMAILDJ_REAL_PROVIDER=openai \
OPENAI_API_KEY=<key> \
python hub-api/scripts/real_mode_smoke.py
```

Pass criteria: generation completes, offer_lock appears in output, CTA lock enforced.

### 3.3 Extension Build Verification

```bash
cd chrome-extension
npm run build
# Confirm dist/ is generated without errors
# Load unpacked in Chrome and verify side panel opens on Gmail
```

---

## Phase 4 — Post-Release

### 4.1 Nightly Judge Eval

The scheduled CI job (`real-mode-nightly`) runs automatically at 07:00 UTC.
After a release, confirm the first nightly run after deployment succeeds:

| Step | Pass Criteria |
|---|---|
| Full judge eval (real) | Judge score ≥ threshold from last calibration |
| Judge calibration | Completes without threshold violations |
| Drift guard | No drift detected vs previous nightly metadata |

See `docs/judge_eval_runbook.md` for drift triage.

### 4.2 Rollback Procedure

If any post-release gate fails:

1. Check `docs/ops/runbooks.md` RB-01 (provider outage) or RB-03 (repair loop latency) as applicable.
2. Revert the merge commit on main (`git revert <merge_sha>`).
3. Re-run Phase 1 gates on the revert.
4. Merge the revert and monitor nightly.

---

## Checklist Quick Reference

Copy-paste for PR description:

```
## Release Checklist
- [ ] CI `checks` job green
- [ ] Surface contract gate passes
- [ ] Doc freshness gate passes
- [ ] Lock compliance smoke passes (if email_generation/ changed)
- [ ] Pairwise regression gate passes (if prompts.py/rubric.py changed)
- [ ] Mock e2e smoke passes
- [ ] Extension build passes
- [ ] CHANGELOG / ADR updated (if invariant changed)
```
