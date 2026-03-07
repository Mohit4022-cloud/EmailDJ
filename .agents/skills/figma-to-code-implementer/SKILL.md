---
name: figma-to-code-implementer
description: Translate Figma designs into EmailDJ frontend code without stylistic drift. Use when given a Figma frame, selection, handoff, or screenshot that should be implemented faithfully in the repo. Map Figma tokens, components, and layout to the existing codebase, preserve spacing and states, and reuse components instead of improvising.
---

# Figma To Code Implementer

## Overview

Implement design intent faithfully. Do not "improve" the design by inventing a new style language. Reuse the repo's existing components and CSS patterns when they fit, and standardize new primitives when they repeat.

## Workflow

1. Check whether a Figma MCP server is available. If it is, use it first for frame context, variables, components, spacing, and states.
2. If Figma MCP is unavailable, fall back to the user's screenshot or written spec and clearly note what could not be verified.
3. Inspect the target UI surface before editing:
   - `frontend/src/main.js`
   - `frontend/index.html`
   - `frontend/src/components/EmailEditor.js`
   - `frontend/src/components/SliderBoard.js`
   - `frontend/src/components/SDRPresetLibrary.js`
4. Map the design into existing repo pieces:
   - shell, hero, and panel layout
   - field groups and actions
   - editor workspace
   - sliders
   - preset modal or selection flow
5. Preserve:
   - spacing rhythm
   - alignment
   - hierarchy
   - interactive states
   - reusable component boundaries
6. If the design changes page structure, use `$ui-architect` first. If the implementation introduces repeated ad hoc styles, run `$design-system-guardian`.

## Repo Rules

- `frontend/` is the primary target.
- Reuse `EmailEditor`, `SliderBoard`, and `SDRPresetLibrary` when the design fits them.
- Do not add one-off visual treatments to only one button, one card, or one field group unless the design explicitly calls for it.
- Keep draft-generation state, remix state, runtime status, and source visibility aligned with the design. Do not hide system status just to make the page cleaner.
- When the design adds a new reusable primitive, name and structure it so Storybook/test coverage can be added later.

## Commands

```bash
rg -n "EmailEditor|SliderBoard|SDRPresetLibrary" frontend/src -g '*.js'
sed -n '1,260p' frontend/src/main.js
sed -n '1,260p' frontend/index.html
```

## References

- Read `references/mapping-rules.md` before implementing a non-trivial frame or selection.
