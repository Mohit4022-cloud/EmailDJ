# EmailDJ Preset Contract

## Invariants for the same request

For traces that share the same normalized request hash:

- `MessagingBrief` facts and hooks should stay the same
- `used_hook_ids` should stay the same
- locked CTA text should stay the same
- grounded proof should not disappear

Treat drift in those fields as a regression unless there is explicit evidence that the underlying request or brief changed.

## Allowed variation

Presets and sliders may legitimately change:

- tone and formality
- framing and assertiveness
- length, sentence count, and subject wording
- body phrasing that still respects the same brief and CTA lock

## Suspicious variation

Flag these as suspicious and explain them:

- `selected_angle_id` changes for the same request
- proof is present in one variant and missing in another
- final CTA line differs from the locked CTA line
- one preset introduces generic opener or template leakage that the others do not

## Source files

- `web-app/src/data/sdrPresets.js`
- `web-app/src/style.js`
- `backend/app/engine/presets/registry.py`
- `backend/debug_traces/**`
