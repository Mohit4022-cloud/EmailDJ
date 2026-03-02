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

## Guardrails

- Claim verification and rewriting: `email_generation/claim_verifier.py`
- Deterministic CTA generation: `email_generation/cta_templates.py`
- Repetition/fluff compression: `email_generation/text_postprocess.py`
- Main generator validation/repair integration: `email_generation/remix_engine.py`
- Preview batch guardrails alignment: `email_generation/preset_preview_pipeline.py`

## Slider Mappings

Deterministic behavior is enforced in `generation_plan.py`:

- `Formal ↔ Casual`: contractions, greeting style, vocabulary selection.
- `Problem ↔ Outcome`: sentence ordering and opener framing.
- `Short ↔ Long`: target word-count bands `55-75`, `75-110`, `110-160`.
- `Bold ↔ Diplomatic`: CTA directness and phrasing.

## Running Tests

```bash
cd /Users/mohit/EmailDJ/hub-api
pytest -q
```

```bash
cd /Users/mohit/EmailDJ/web-app
npm test
```

