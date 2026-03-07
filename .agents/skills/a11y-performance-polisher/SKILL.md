---
name: a11y-performance-polisher
description: Run the final EmailDJ frontend polish pass after implementation. Use when a UI change is nearly done and needs keyboard-flow, focus-state, contrast, responsiveness, layout-shift, slow-interaction, console-error, and performance verification before merge or handoff.
---

# A11y Performance Polisher

## Overview

This skill runs after implementation. Verify that the UI works cleanly for keyboard users, holds up across screen sizes, and does not feel slow or unstable.

## Workflow

1. Prefer browser tooling when available:
   - Playwright MCP for keyboard flow and responsive interaction checks
   - Chrome DevTools MCP for console, network, trace, layout shift, and performance inspection
2. If MCP tooling is unavailable, fall back to:
   - local tests
   - local build
   - static inspection of focus states, semantic structure, and responsive layout rules
3. Check, in order:
   - keyboard flow and tab order
   - focus visibility
   - contrast and state clarity
   - mobile and desktop layout behavior
   - loading and disabled states
   - console or network errors
   - layout shift and sluggish interactions
4. Report what was verified and what remains a tooling gap.
5. If the change touches both `frontend/` and `web-app/`, verify both surfaces.

## Output

Return exactly these headings:

- `blocking`
- `polish`
- `verification_gaps`

## Commands

```bash
npm --prefix frontend test
npm --prefix frontend build
npm --prefix web-app test
npm --prefix web-app build
```

## References

- Read `references/verification-checklist.md` before signing off on a UI change.
