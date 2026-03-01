# EmailDJ Follow-Up Tasks

## TASK-001 — Provider Failure Alert Sink Integration

**Created:** 2026-02-28
**Source:** Entry 006 validation run (`docs/CHRONICLE.md`)
**Priority:** High
**Status:** Open

### Problem

`quick_generate.py` logs provider failure events and threshold breaches, but there is no external incident sink when `QUICK_PROVIDER_FAILURE_ALERT_THRESHOLD` is exceeded.

### Required Outcome

When failure threshold is exceeded for a provider/day window, emit an actionable external alert while preserving current API/SSE behavior.

### Acceptance Criteria

1. On threshold breach, send structured alert payload to configured sink (Slack webhook and/or metrics endpoint).
2. Alert includes provider, daily failure count, threshold, timestamp, and environment.
3. Duplicate alerts are suppressed per provider/day unless count increases by a configured step.
4. Existing routes and SSE contracts remain unchanged.
5. Integration tests cover threshold crossing and sink invocation behavior.
