# Email Presets

<!-- AUTO-DRAFTED: review before merge -->

Source: `hub-api/email_generation/preset_strategies.py`, `docs/EmailDJ SDR Presets.md`
Last reviewed: 2026-03-02

Presets are named generation strategies that shape the structure and hook approach of a
generated email. They constrain HOW an email is built — not WHAT it says. Content is always
grounded in `offer_lock` and `allowed_facts`; presets cannot override compliance invariants.

For the engineering field-level reference, see [`docs/policy/prompt_contracts.md`](../policy/prompt_contracts.md).
For the supplementary product/EQ framing, see [`docs/EmailDJ SDR Presets.md`](../EmailDJ SDR Presets.md).

---

## What Presets Are

A preset maps to a `PresetStrategy` object in `hub-api/email_generation/preset_strategies.py`
with these fields:

- **`preset_id`** — machine identifier (snake_case, used in API requests)
- **`label`** — display name shown in the UI
- **`hook_type`** — how the email opens (the "wedge")
- **`cta_type`** — default CTA intent
- **`structure_template`** — ordered tuple of structural blocks
- **`narrative`** — one-sentence description of the strategy's goal

Presets are deterministic: the same preset + offer_lock + prospect data always produces the
same structural plan. The LLM fills in the content.

---

## What Presets Are NOT

- Presets cannot override `offer_lock` — the pitch anchor is always set by the caller.
- Presets cannot override `cta_lock` — if a CTA lock is set, it takes precedence over the
  preset's default `cta_type`.
- Presets do not control tone or length — those are controlled by `WebStyleProfile` sliders.
- Presets are not "tones" or "personalities" — they are structural strategies.

---

## Preset Registry

Currently 6 canonical presets are registered in code. The product ships 10 labeled presets
(aliases 1–10), with aliases 6, 7, 9, 10 resolving to existing canonical IDs.

| Preset ID | Label | Hook Type | CTA Type | Structure | Volume Rank |
|---|---|---|---|---|---|
| `straight_shooter` | Straight Shooter | `direct_wedge` | `time_ask` | problem → outcome → proof → cta | #1 |
| `headliner` | Headliner | `curiosity_headline` | `time_ask` | hook → problem → proof → cta | #2 |
| `giver` | Giver | `value_first` | `value_asset` | hook → outcome → proof → cta | #3 |
| `challenger` | Challenger | `contrarian_risk` | `pilot` | problem → hook → outcome → cta | #4 |
| `industry_insider` | Industry Insider | `domain_pattern` | `value_asset` | hook → problem → proof → cta | #5 |
| `c_suite_sniper` | C-Suite Sniper | `executive_brief` | `time_ask` | outcome → proof → cta | #8 |

### Numeric Alias → Canonical ID Mapping

| Alias | Resolves to |
|---|---|
| 1, "the straight shooter" | `straight_shooter` |
| 2, "the headliner" | `headliner` |
| 3, 6, "the giver" | `giver` |
| 4, "the challenger" | `challenger` |
| 5, 7, 10, "the industry insider" | `industry_insider` |
| 8, "the c-suite sniper" | `c_suite_sniper` |
| 9, "the visionary" | `headliner` |

---

## Slider Mapping

Slider ranges below are the product-recommended defaults per preset.
Values are on the Web App's 0–100 scale (0 = left pole, 100 = right pole).

| Preset | Formality (Casual↔Formal) | Orientation (Problem-Led↔Outcome-Led) | Length (Short↔Long) | Assertiveness (Diplomatic↔Bold) |
|---|---|---|---|---|
| Straight Shooter | 60 (formal-leaning) | 50 (balanced) | 40 (short-leaning) | 60 (bold-leaning) |
| Headliner | 40 (casual-leaning) | 90 (outcome-led) | 60 (long-leaning) | 80 (bold) |
| Giver | 20 (casual) | 60 (outcome-leaning) | 30 (short) | 0 (diplomatic) |
| Challenger | 40 (casual-leaning) | 0 (problem-led) | 40 (short-leaning) | 100 (bold) |
| Industry Insider | 50 (neutral) | 60 (outcome-leaning) | 75 (long) | 15 (diplomatic-leaning) |
| C-Suite Sniper | 70 (formal) | 80 (outcome-led) | 0 (shortest) | 80 (bold) |

---

## Hook Types

| Hook Type | What It Does |
|---|---|
| `direct_wedge` | Opens with a specific problem statement anchored to the prospect's situation |
| `curiosity_headline` | Opens with a compelling, curiosity-inducing statement |
| `value_first` | Opens by offering something useful before making any ask |
| `contrarian_risk` | Opens by challenging a prevailing assumption or framing inaction as risk |
| `domain_pattern` | Opens with an observed industry pattern using domain-specific language |
| `executive_brief` | Opens with a concise, executive-style outcome statement (no fluff) |

---

## Governance

### Adding a New Preset

1. Add a `PresetStrategy` entry to `PRESET_STRATEGIES` in `hub-api/email_generation/preset_strategies.py`
2. Add all relevant numeric and name aliases to `_PRESET_ALIASES`
3. Add a row to the Preset Registry table above
4. Add slider defaults to the Slider Mapping table above
5. Update `docs/EmailDJ SDR Presets.md` with product-facing EQ/vibe description
6. If the preset introduces a **new `hook_type` or `cta_type`**, create an ADR in `docs/adr/`
7. Run the full judge eval: `./scripts/eval:judge:full` — preset output must pass all compliance gates

### Deprecating a Preset

Presets cannot be silently removed — their `preset_id` may be stored in user sessions.
To deprecate:
1. Keep the `PresetStrategy` entry (it remains in the alias registry)
2. Mark it as deprecated in this doc
3. Remove it from the UI preset library in the web app
4. Add an ADR explaining the deprecation rationale

### Who Can Add Presets

Any engineer can add a preset. An ADR is only required if a new `hook_type` or `cta_type`
is introduced (these affect the generation plan IR and prompt contract). Purely additive
presets using existing hook/CTA types do not require an ADR.
