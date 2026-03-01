# EmailDJ Follow-Up Tasks

## TASK-001 — Provider Failure Alert Sink Integration

**Created:** 2026-02-28
**Source:** Entry 006 validation run (`docs/CHRONICLE.md`)
**Priority:** High
**Status:** Done
**Completed:** 2026-03-01

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

---

## TASK-002 — Replace Mock Campaign Intelligence with Real Provider Adapters

**Created:** 2026-03-01
**Source:** VP campaign mock-intelligence gap review (`hub-api/agents/nodes/crm_query_agent.py`, `hub-api/agents/nodes/intent_data_agent.py`, `hub-api/agents/graph.py`)
**Priority:** High
**Status:** Done
**Completed:** 2026-03-01

### Problem

VP campaign creation/approval relied on hardcoded mock CRM and intent data, preventing production use of configured external intelligence providers.

### Required Outcome

Introduce provider interfaces and env-driven adapter resolution for CRM + intent data while preserving explicit fallback behavior and campaign endpoint contracts.

### Acceptance Criteria

1. CRM and intent nodes use provider adapters with env configuration and real-provider support.
2. Default mode prefers real providers when configuration is present; explicit `fallback` mode remains available.
3. Campaign create/approve flows continue to work without contract changes.
4. Integration tests cover create/approve with provider stubs and fallback behavior.

---

## TASK-003 — VP Approval Gate Hardening + Audit Trail

**Created:** 2026-03-01
**Source:** VP campaign approval hardening review (`hub-api/api/routes/campaigns.py`)
**Priority:** High
**Status:** Done
**Completed:** 2026-03-01

### Problem

Campaign approval was a simple state flip without approver identity checks, role enforcement, or immutable approval history.

### Required Outcome

Make approval a policy-enforced, auditable gate before assignments can be created.

### Acceptance Criteria

1. Approval requires authenticated approver identity and VP/admin role check.
2. Approval record persists `campaign_id`, `approver_id`, timestamp, audience count, and approval reason.
3. Approval is invalidated when audience or sequence content changes after approval.
4. Assignment endpoint blocks unless latest approval is valid.
5. Integration tests cover unauthorized approval, valid approval, post-approval mutation invalidation, and assignment blocking.
