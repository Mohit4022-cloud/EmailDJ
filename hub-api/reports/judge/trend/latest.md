# Judge Trend Report

- Generated at: `2026-03-02T16:06:52.828546Z`
- Mode: `smoke`
- Samples: `2`

## What Got Worse

- Comparing current `stability-check` vs previous `stability-proof`

| Metric | Previous | Current | Delta |
|---|---:|---:|---:|
| overall_mean | 4.4800 | 3.9300 | -0.5500 |
| relevance_mean | 4.0000 | 4.0000 | +0.0000 |
| credibility_mean | 4.0000 | 3.4000 | -0.6000 |
| overclaim_fail_count | 0 | 1 | +1 |
| pass_rate | 0.8000 | 0.8000 | +0.0000 |

## Top 5 Rising Failure Flags

| Signal | Previous | Current | Delta |
|---|---:|---:|---:|
| clarity_violation_detected | 0 | 5 | +5 |
| clarity_violation_present | 0 | 5 | +5 |

## Most Regressed 10 Cases

| Case ID | Δ Overall | Δ Relevance | Δ Credibility | Pass/Fail | Snippet |
|---|---:|---:|---:|---|---|
| lc_001 | -0.6300 | +0.0000 | -1.0000 | pass->pass | Hi Alex, Acme is navigating priorities that make it hard to engage target accounts with the right message at the right time. Based on rec... |
  - Rationale: Relevance scored 4/5 based on prospect and offer alignment.
| lc_007 | -0.6300 | +0.0000 | -1.0000 | pass->pass | Hi Alex, Nimbus Data teams focused on message relevance tend to see stronger engagement from priority accounts. Based on recent activity,... |
  - Rationale: Relevance scored 4/5 based on prospect and offer alignment.
| lc_013 | -0.6300 | +0.0000 | -1.0000 | pass->pass | Hi Alex, Altair Works is navigating priorities that make it hard to engage target accounts with the right message at the right time. Base... |
  - Rationale: Relevance scored 4/5 based on prospect and offer alignment.
| lc_019 | -0.6300 | +0.0000 | -1.0000 | pass->pass | Hi Alex, Bluebird Systems teams focused on message relevance tend to see stronger engagement from priority accounts. Based on recent acti... |
  - Rationale: Relevance scored 4/5 based on prospect and offer alignment.
| lc_025 | -0.2300 | +0.0000 | +1.0000 | fail->fail | Hi Alex, Acme is navigating priorities that make it hard to engage target accounts with the right message at the right time. Based on rec... |
  - Rationale: Relevance scored 4/5 based on prospect and offer alignment.

## Recommended Next Prompt Adjustments

- None

## History

| Candidate | Model | Version | Overall | Relevance | Credibility | Overclaim fails | Pass rate | Δ Overall | Δ Relevance | Δ Credibility | Δ Overclaim | Δ Pass rate |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stability-proof | gpt-4.1-nano | gpt-4.1-nano | 4.480 | 4.000 | 4.000 | 0 | 0.800 | +0.000 | +0.000 | +0.000 | +0 | +0.000 |
| stability-check | gpt-4.1-mini | gpt-4.1-mini | 3.930 | 4.000 | 3.400 | 1 | 0.800 | -0.550 | +0.000 | -0.600 | +1 | +0.000 |
