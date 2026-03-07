---
name: design-system-guardian
description: Prevent EmailDJ frontend styling chaos. Use when adding or reviewing UI styles, primitives, or reusable components so one-off colors, radius values, shadows, spacing, and ad hoc button/card/input treatments do not spread. Enforce token naming, standardize primitives, and reject undocumented style exceptions.
---

# Design System Guardian

## Overview

Act as the anti-chaos pass. Standardize repeated styling decisions and stop ad hoc values from becoming the system by accident.

## Workflow

1. Audit the touched UI surface first, especially `frontend/index.html` and any new component files.
2. Collect repeated literals for:
   - colors
   - spacing
   - border radius
   - shadows
   - typography treatments
3. Decide whether each finding is:
   - `blocking`
   - `should-standardize`
   - `allowed-exception`
4. Require a documented reason for any exception that stays ad hoc.
5. If the request is a broader redesign, pair this skill with `$ui-architect`. If the task is implementation from design, pair it with `$figma-to-code-implementer`.

## Repo Rules

- The repo currently relies heavily on inline CSS in `frontend/index.html`.
- Repeated radius and shadow values are token candidates by default.
- Buttons, cards, inputs, labels, badges, alerts, and panel shells should converge on shared primitives instead of independent styling blocks.
- Prefer extending existing CSS variables before introducing new literals.
- Reject styling that only exists because it was faster to paste inline.

## Output

Return findings under exactly these headings:

- `blocking`
- `should-standardize`
- `allowed-exceptions`

## Commands

```bash
rg -n "border-radius|box-shadow|#[0-9A-Fa-f]{3,6}|rgba\\(" frontend/index.html frontend/src
sed -n '1,260p' frontend/index.html
find frontend/src/components -maxdepth 1 -type f | sort
```

## References

- Read `references/token-audit-checklist.md` before approving new style values.
