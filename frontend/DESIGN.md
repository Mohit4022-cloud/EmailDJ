# Remix Studio Design Notes

## Page principles

- The workspace is the product. Seller and prospect inputs exist to feed a stable messaging brief, not to compete with the draft.
- Presets and sliders are expression controls. They should visually communicate "same brief, different delivery."
- Trust is a first-class surface. Runtime mode, stage progress, validators, trace metadata, and sources should stay visible without digging.
- The UI should feel premium and calm: generous spacing, layered surfaces, restrained color, strong typography, and minimal decorative noise.

## Token categories

- Colors: warm neutral backgrounds, bright accent for action, cool accent for trust/status, explicit success/warning/danger states.
- Surfaces: one shell background plus layered cards/panels with consistent border, radius, and shadow treatment.
- Spacing: use the shared scale in `src/styles.css` rather than arbitrary pixel values.
- Typography: `Avenir Next`-led sans stack for product UI and `IBM Plex Mono`-style mono stack for trace/hash identifiers.

## Component rules

- Buttons: primary actions use the accent gradient; secondary actions stay quiet and neutral.
- Inputs: use shared rounded field styling with strong focus rings and no inline styling.
- Panels: keep seller/prospect sections, workspace, and diagnostics on the same surface system.
- Diagnostics: status, trace, validators, and sources should render real backend payloads, not inferred placeholders.
- Motion: use subtle hover/lift and loading shimmer only when it adds state clarity.
