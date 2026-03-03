# Validator Rules

<!-- AUTO-DRAFTED (Tier 2): review for completeness before merge -->

Source: `hub-api/email_generation/compliance_rules.py`, `hub-api/email_generation/output_enforcement.py`

All violation codes emitted as `violation_codes` in the SSE `done` event and in `WebPreviewBatchMeta`.

---

## Violation Code Registry

### Offer Lock Violations

| Code | Trigger | Severity | Source |
|---|---|---|---|
| `offer_lock_missing` | `offer_lock` text absent from subject + body | Hard | `output_enforcement.py` |
| `offer_lock_body_verbatim_missing` | `offer_lock` text absent from body specifically | Hard | `output_enforcement.py` |
| `forbidden_other_product_mentioned:<product>` | Another product/offering name found in output | Hard | `output_enforcement.py` |

**Why**: The product can only pitch one thing per email. Multiple pitches dilute the message and violate SDR playbook discipline.

### CTA Lock Violations

| Code | Trigger | Severity | Source |
|---|---|---|---|
| `cta_lock_not_used_exactly_once` | CTA lock text missing or appears more than once | Hard | `output_enforcement.py` |
| `cta_near_match_detected` | Close-but-not-exact match of CTA lock text found | Warning | `output_enforcement.py` |
| `additional_cta_detected` | Secondary CTA detected (duration pattern + channel hints + ask cues) | Hard | `compliance_rules.py` |

**Why**: Prospect confusion from multiple CTAs reduces reply rates. Exact CTA lock ensures SDR-authored calls-to-action are preserved verbatim.

### Greeting Violations

| Code | Trigger | Severity | Source |
|---|---|---|---|
| `greeting_missing_or_invalid` | No greeting detected at email start | Hard | `output_enforcement.py` |
| `greeting_first_name_mismatch` | Greeting uses wrong name vs prospect first name | Hard | `output_enforcement.py` |
| `greeting_not_first_name_only` | Greeting uses full name or title instead of first name only | Warning | `output_enforcement.py` |

### Internal Leakage Violations

| Code | Trigger | Severity | Source |
|---|---|---|---|
| `internal_leakage_term:<term>` | A term from `_NO_LEAKAGE_TERMS` appears in output | Hard | `compliance_rules.py` |

**Banned terms** (from `compliance_rules._NO_LEAKAGE_TERMS`):
`emaildj`, `remix`, `mapping`, `template`, `templates`, `slider`, `sliders`, `prompt`, `prompts`, `llm`, `llms`, `openai`, `gemini`, `codex`, `generated`, `automation tooling`

**Why**: These terms reveal the AI tooling behind the email. Prospects must not infer automation.

### Claims Policy Violations

| Code | Trigger | Severity | Pattern source |
|---|---|---|---|
| `cash_equivalent_cta_detected` | Gift card / cash reward / prepaid card CTA found | Hard | `_CASH_CTA_PATTERN` |
| `unsubstantiated_statistical_claim` | Stat claim (e.g. "40% increase") not in research text | Hard | `_STAT_CLAIM_PATTERN` |
| `unsubstantiated_performance_claim` | Guaranteed ROI claim (e.g. "guaranteed results") | Hard | `_GUARANTEED_CLAIM_PATTERN` |
| `unsubstantiated_claim:<claim>` | Absolute revenue/pipeline claim not in research | Hard | `_ABSOLUTE_REVENUE_PATTERN` |

**Why**: Unsubstantiated claims are legally and reputationally risky. All quantified claims must be traceable to the research text provided by the SDR.

### Length Violations

| Code | Trigger | Severity |
|---|---|---|
| `length_out_of_range:{actual}_expected_{min}_{max}` | Body word count outside slider-defined band | Warning or Hard |

### Prospect Reference Violations

| Code | Trigger | Severity |
|---|---|---|
| `prospect_reference_missing` | Body does not reference any prospect identity marker (name, company, title) | Warning |

---

## Enforcement Levels

Configured by `EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL` (source: `runtime_policies.py`):

| Level | Behavior |
|---|---|
| `warn` | Return draft with violations metadata. No retry. |
| `repair` | Trigger repair loop (re-generate with violation context). Return draft if repair succeeds. |
| `block` | Hard-fail on any Hard-severity violation. Return error event. |

Repair loop enabled/disabled by `EMAILDJ_REPAIR_LOOP_ENABLED`.

---

## CTA Detection Heuristics (`compliance_rules.py`)

Secondary CTA is detected when output contains BOTH:
- A duration pattern (e.g. "15-minute", "30 min") via `_CTA_DURATION_PATTERN`, OR a channel hint (call, meeting, demo, pilot…) via `_CTA_CHANNEL_HINTS`
- An ask cue (open to, would you, could we…) via `_CTA_ASK_CUES`

This heuristic is intentionally conservative — it may produce false positives on unusual phrasing. Tune via repair loop, not by loosening the rules.
