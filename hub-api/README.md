# EmailDJ Hub API Notes

## Generation Plan IR

`email_generation/generation_plan.py` introduces a deterministic plan object used before draft rendering.

- `GenerationPlan` fields:
  - `greeting`
  - `hook_type`
  - `wedge_problem`
  - `wedge_outcome`
  - `proof_points_used`
  - `objection_guardrails`
  - `tone_style`
  - `length_target`
  - `cta_type`
  - `banned_phrases`
- Preset strategy mapping is defined in `email_generation/preset_strategies.py`.
- The plan is serialized into session state as `generation_plan`.

## Preset Preview Cache (Web App)

Preset preview cache behavior is implemented in:

- `web-app/src/components/presetPreviewUtils.js`
- `web-app/src/components/SDRPresetLibrary.js`

Preview entries are keyed by:

- hash of normalized context:
  - prospect fields
  - `prospect_first_name`
  - deep research paste
  - company notes
  - offer lock + product context
  - slider values
  - `cta_type`
  - `cta_lock_text`
- plus `preset_id`

The modal can be opened/closed repeatedly without re-generation for unchanged keys. Rapid preview scheduling is debounced and in-flight requests are coalesced by context hash.

## CTA Precedence

CTA precedence is unified across generate + preview:

1. If CTA lock text is non-empty: use it exactly (hard override).
2. Else if `cta_type` is provided: use that CTA template.
3. Else: use preset default `cta_type`.

Relevant files:

- `email_generation/cta_templates.py`
- `email_generation/generation_plan.py`
- `email_generation/preset_preview_pipeline.py`
- `web-app/src/components/presetPreviewUtils.js`

## Guardrails

- Claim verification and rewriting: `email_generation/claim_verifier.py`
- Deterministic CTA generation: `email_generation/cta_templates.py`
- Repetition/fluff compression: `email_generation/text_postprocess.py`
- Main generator validation/repair integration: `email_generation/remix_engine.py`
- Preview batch guardrails alignment: `email_generation/preset_preview_pipeline.py`
- Shared post-render enforcement: `email_generation/output_enforcement.py`

## Long-Mode Expansion + Repetition Guards

Long mode no longer pads with repeated filler lines.

- Expansion strategy now appends unique blocks from a controlled pool:
  - proof point(s) from company notes / allowed facts
  - mechanism line (`Search, Enrich, Act`)
  - first-week deliverable line
  - risk framing line
- Word-count fitting uses finite composition (no looped sentence padding).
- Guards:
  - sentence-level dedupe (same sentence max once)
  - repeated 3-5 word ngram cap

Relevant files:

- `email_generation/output_enforcement.py`
- `email_generation/generation_plan.py`
- `email_generation/remix_engine.py`
- `email_generation/preset_preview_pipeline.py`

## Generic AI-Initiatives Opener Guard

Generic opener forms like "As <company> scales its enterprise AI initiatives..." are blocked by default.

- Allowed only when both:
  - deep research explicitly contains that phrasing
  - hook strategy is `research_anchored`
- Otherwise replaced deterministically with risk/domain/outcome opener variants.

Relevant files:

- `email_generation/output_enforcement.py`
- `email_generation/remix_engine.py`
- `email_generation/preset_preview_pipeline.py`

## Claim Verification Scope

Numeric-claim policy:

- Numeric claims are allowed only when extracted from company notes.
- Disallowed numeric claims are rewritten/removed.

Applied surfaces:

- main generate/remix: subject + body
- preset preview: subject + body + `whyItWorks` + vibe labels/tags

Relevant files:

- `email_generation/claim_verifier.py`
- `email_generation/generation_plan.py`
- `email_generation/preset_preview_pipeline.py`

## Slider Mappings

Deterministic behavior is enforced in `generation_plan.py`:

- `Formal ↔ Casual`: contractions, greeting style, vocabulary selection.
- `Problem ↔ Outcome`: sentence ordering and opener framing.
- `Short ↔ Long`: target word-count bands `55-75`, `75-110`, `110-160`.
- `Bold ↔ Diplomatic`: CTA directness and phrasing.

## Running Tests

```bash
cd /Users/mohit/EmailDJ/hub-api
pytest -q tests/test_claim_verifier.py tests/test_output_enforcement.py tests/test_ctco_validation.py tests/test_preset_preview_pipeline.py
```

```bash
cd /Users/mohit/EmailDJ/web-app
npm test
```
