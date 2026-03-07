# Acceptance Checklist

## A) UI parity
- [x] Left inputs + right sliders/output layout preserved.
- [x] Generate writes a draft in right panel.
- [x] Copy copies clean subject+body text.

## B) Target account enrichment
- [x] AI button triggers SSE enrichment.
- [x] Target enrichment fills profile and appends cited deep-research block.
- [x] Last refreshed timestamp shown.
- [x] Refresh bypass supported.
- [x] Unknown fallback for unsupported fields.

## C) Prospect enrichment
- [x] Prospect AI requires target company anchor.
- [x] Produces role summary, talking points, cited news.
- [x] Refresh bypass supported.

## D) Remix stability
- [x] Generate-once compile to blueprint.
- [x] Remix uses stored blueprint (no deep-research re-ingest).
- [x] CTA lock exact-match validator.
- [x] Repetition + truncation validators and repair loop.

## E) Preset library
- [x] Selected preset preview starts first.
- [x] Remaining previews fill concurrently (cap=3).
- [x] Diversity validator available for preview sets.

## F) Debuggability
- [x] Stream done payload includes `trace_id`, `prompt_template_hash`, `prompt_template_version`.
- [x] Validation metadata included in done payload.
- [x] Sources included in done payload and shown in UI dropdown.
