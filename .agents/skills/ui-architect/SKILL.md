---
name: ui-architect
description: Plan and restructure EmailDJ product UI before coding. Use when redesigning screens, reviewing screenshots, or making the app feel premium, world-class, polished, lower-cognitive-load, or less form-heavy. Decide page structure, progressive disclosure, hierarchy, spacing rhythm, empty states, loading states, and status placement before implementation.
---

# UI Architect

## Overview

Act as the top-level product UI brain for EmailDJ. Reduce cognitive load before discussing code. Prefer fewer visible controls at once and make the current task visually obvious.

## Workflow

1. Inspect the current UI surface before proposing changes:
   - `frontend/src/main.js`
   - `frontend/index.html`
   - `frontend/src/components/*.js`
2. Identify the user's active job, the current distractions, and which controls do not need to be visible immediately.
3. Produce a structure-first plan before implementation details:
   - page sections
   - step flow or progressive disclosure
   - where draft preview, controls, status, empty states, and loading states live
   - which controls move into accordions, drawers, modal flows, or advanced sections
4. Keep the draft/editor area at least as prominent as the input controls.
5. If the request includes a Figma frame or a design handoff, route implementation to `$figma-to-code-implementer` after the structure is settled.

## Repo Rules

- Treat `frontend/` as canonical. Reference `web-app/` only when duplication matters.
- The current pain points live in the long input panel in `frontend/src/main.js`.
- Default to grouping the UI into:
  - seller context
  - prospect context
  - research/enrichment
  - preset or slider controls
  - draft workspace
- Prefer staged reveal over dumping all seller and prospect fields at once.
- Keep status text and runtime badges close to the generation/remix workspace instead of detached at the top of the page.
- Define empty states, loading states, and post-generate states explicitly. Do not leave them implied.

## Output

Return exactly these headings when doing planning work:

- `current_issues`
- `proposed_structure`
- `visibility_strategy`
- `state_placement`
- `implementation_order`

## Commands

```bash
sed -n '1,260p' frontend/src/main.js
sed -n '1,260p' frontend/index.html
find frontend/src/components -maxdepth 1 -type f | sort
```
