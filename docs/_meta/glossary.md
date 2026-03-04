# Glossary

Canonical vocabulary for EmailDJ. Use these terms consistently across all docs, code comments,
and ADRs. Do not introduce synonyms without updating this file.

---

## ADR
Architecture Decision Record. A file in `docs/adr/` capturing why a durable technical
policy or invariant was introduced or changed. Required when any `adr.core_paths` file changes.

## context_vault
The Redis-backed cache (TTL 1hr, backed by Postgres + Pinecone) that stores enriched account
intelligence extracted from CRM data. Lives in `hub-api/context_vault/`.

## CTA Lock (`cta_lock`)
The exact call-to-action string that must appear once and only once in the generated email body.
Non-negotiable invariant enforced at output layer. See `docs/policy/control_contract.md`.

## CTCO
The combined constraint set applied during generation validation: greeting check, CTA lock,
offer lock, compliance rules, output format, and runtime policy checks.

## delegation_engine
The VP-facing assignment subsystem (`hub-api/delegation/`) that routes campaign accounts to
individual SDRs and surfaces them in the side panel assignment queue.

## doc_rot
State where a doc's content diverges from the code it describes because the code changed
without a corresponding doc update. Caught by `hub-api/scripts/doc_freshness_check.py`.

## Enforcement Level
Runtime policy mode (`warn | repair | block`) controlling whether lock/compliance violations
are logged only, automatically repaired, or cause the generation to be rejected.
Set via `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL`. See `hub-api/email_generation/runtime_policies.py`.

## freshness_check
The CI gate that compares changed code files against their bound docs. Fails if bound code
changed without a corresponding doc update. Script: `hub-api/scripts/doc_freshness_check.py`.

## gold_set
The canonical evaluation dataset (`hub-api/evals/gold_set.full.json`) used to measure
generation quality in the judge pipeline. The smoke subset is `gold_set.smoke_ids.json`.

## hub_api
The FastAPI backend service (`hub-api/`) that orchestrates email generation, campaign
management, context vault operations, and webhook capture. The central spoke in the
hub-and-spoke architecture.

## judge_pipeline
The LLM-as-judge evaluation framework (`hub-api/evals/judge/`) that scores generated emails
against the gold set using a rubric. Runs in mock mode on every PR, real mode nightly.

## model_cascade
The tiered model selection strategy for generation:
- Tier 1 (highest quality): GPT-4o / Claude Opus 4.6 / Llama 3.3 70B
- Tier 2 (balanced): GPT-5-nano / Claude 3.5 Haiku / Llama 3.3 70B
- Tier 3 (fallback): same as Tier 2
Provider preference set via `EMAILDJ_REAL_PROVIDER`. See `hub-api/email_generation/model_cascade.py`.

## mode
The generation mode controlling whether real LLM calls are made:
- `mock`: returns deterministic stub outputs (default, no API keys needed)
- `real`: calls live provider APIs
Controlled by `EMAILDJ_QUICK_GENERATE_MODE`.

## Offer Lock (`offer_lock`)
The single product/offering string that the draft is exclusively allowed to pitch.
Acts as the sole pitch anchor — `current_product` in company context is informational only.
Non-negotiable invariant enforced at output layer. See `docs/policy/control_contract.md`.

## PII_prefilter
Layer 1 of the 3-layer PII defense. Runs in the Chrome Extension browser context before any
data leaves the device. Uses regex patterns to redact EMAIL, PHONE, SSN, CREDIT CARD.
Returns `{ redacted, tokenMap }`. See `chrome-extension/src/content-scripts/pii-prefilter.js`.

## preset
A named generation strategy that maps to a specific hook type, CTA type, and email structure.
Presets are deterministic; they constrain the generation plan, not the content.
Registry: `hub-api/email_generation/preset_strategies.py`. Docs: `docs/product/presets.md`.

## Presidio
The Microsoft Presidio NER (Named Entity Recognition) library used as Layer 2 of the 3-layer
PII defense in `hub-api/pii/presidio_redactor.py`. Identifies entities missed by the regex
prefilter.

## Preview Batch Pipeline
The preset preview path that generates multiple preset-specific email previews from a single
batch request. Enabled via `EMAILDJ_PRESET_PREVIEW_PIPELINE=on`.
See `hub-api/email_generation/preset_preview_pipeline.py`.

## Repair Loop
The validation retry path that attempts to bring model output back into compliance with all
lock and policy constraints. Controlled by `EMAILDJ_REPAIR_LOOP_ENABLED`.
See `hub-api/email_generation/runtime_policies.py`.

## service_worker
The MV3 Chrome Extension background service worker (`chrome-extension/src/background/service-worker.js`).
Handles message routing and keep-alive. IMPORTANT: it is NOT stateful — the Side Panel is
the stateful process (MV3 architectural constraint).

## session
A stateful generation context on the Hub API keyed by `session_id`. Created by
`POST /web/v1/generate`, consumed by `POST /web/v1/remix` and `POST /web/v1/feedback`.
Sessions persist the draft history and style profile for remix operations.

## side_panel
The Chrome Extension side panel (`chrome-extension/src/side-panel/`) — the primary user
interface embedded in Gmail. It is the stateful process in MV3 (not the service worker).
Streams email tokens, displays the personalization slider, and surfaces campaign assignments.

## SSE
Server-Sent Events — the streaming transport used to deliver email tokens from Hub API to
Extension and Web App. Event types: `start`, `token`, `done`, `error`.
See `docs/contracts/streaming_sse.md` and `hub-api/email_generation/streaming.py`.

## SSE Done Metadata
The final `done` SSE event payload, containing observability fields:
`provider`, `model`, `retry_count`, `repair_count`, `violation_codes`, `latency_ms`.
See `docs/contracts/streaming_sse.md`.

## token_vault
Layer 3 of the 3-layer PII defense. Stores the mapping from PII placeholder tokens (e.g.,
`[EMAIL_1]`) to their original values on the Hub API side.
See `hub-api/pii/token_vault.py`.

## Violation Code
A machine-readable label for a policy or lock check failure, e.g.,
`cta_lock_not_used_exactly_once`, `offer_lock_missing`, `internal_leakage_detected`.
See `docs/policy/validator_rules.md`.
