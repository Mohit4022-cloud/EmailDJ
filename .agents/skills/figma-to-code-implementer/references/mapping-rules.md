# Mapping Rules

Use this reference when translating Figma designs into EmailDJ code.

## Primary Surfaces

- `frontend/src/main.js`
  - page composition
  - form grouping
  - draft workspace placement
  - status and runtime badge placement
- `frontend/index.html`
  - layout CSS
  - spacing and visual language
- `frontend/src/components/EmailEditor.js`
  - editable draft area
  - copy action
  - sources panel
  - draft meta text
- `frontend/src/components/SliderBoard.js`
  - slider block layout
  - slider labels and density
- `frontend/src/components/SDRPresetLibrary.js`
  - preset trigger
  - modal shell
  - preset list and preview structure

## Translation Rules

- Figma section or frame with a distinct task boundary:
  - map to a page section, panel, accordion, drawer, or step
- Figma component repeated 2+ times:
  - make or reuse a primitive instead of copying styles inline
- Figma variants or stateful components:
  - preserve default, hover, focus, disabled, loading, error, and empty states when present
- Figma spacing tokens:
  - map to existing CSS variables first
  - if repeated literals are required, surface them to `$design-system-guardian`
- Figma badge, alert, or status chip:
  - keep it near the relevant working area, not as a disconnected decoration

## Current Repo Hotspots

- The input form is currently dense and uninterrupted.
- The draft workspace can become visually secondary to controls.
- Sliders and preset controls can compete with the main generation flow.
- Status and runtime state need deliberate placement during redesigns.

## Do Not Drift

- Do not replace a provided design with generic "AI app" styling.
- Do not collapse multiple states into one just because the current repo is simpler.
- Do not add novel colors, shadows, or radii without checking whether they should become tokens.
