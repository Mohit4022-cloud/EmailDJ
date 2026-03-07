---
name: frontend-ux-critic
description: Review EmailDJ UI like a senior product designer before code changes. Use when auditing the current interface, pasted screenshots, or a proposed redesign. Identify clutter, weak hierarchy, bad CTA placement, weak grouping, low-signal text, inconsistent spacing, and ranked usability fixes before implementation starts.
---

# Frontend UX Critic

## Overview

Be blunt and specific. Return the ranked fix list first. Do not jump into implementation details until the problems are clearly stated.

## Workflow

1. Inspect the current UI, screenshot, or browser state before proposing fixes.
2. If Playwright or Chrome DevTools MCP is available, prefer a quick interaction pass over static guessing.
3. Review the UI for:
   - hierarchy
   - grouping
   - primary action clarity
   - competing controls
   - helper text quality
   - status placement
   - empty and loading states
4. Rank the findings by user harm, not by ease of fixing.
5. Only after the ranked list is stable should you suggest a redesign path or route to `$ui-architect`.

## Repo Rules

Explicitly check for the recurring EmailDJ issues:

- the long uninterrupted form in `frontend/src/main.js`
- sliders competing with core inputs for attention
- the draft preview or editor feeling secondary
- runtime and status badges floating away from the active work area
- low-signal labels or helper copy that increase cognitive load
- inconsistent spacing rhythm between panels, fields, and actions

## Output

Return exactly these headings:

- `ranked_fixes`
- `why_this_hurts`
- `recommended_direction`

## Commands

```bash
sed -n '1,260p' frontend/src/main.js
sed -n '1,260p' frontend/index.html
find frontend/src/components -maxdepth 1 -type f | sort
```

## References

- Read `references/emaildj-ux-rubric.md` before finalizing findings.
