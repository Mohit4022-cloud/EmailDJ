# Token Audit Checklist

Use this checklist before allowing new frontend styling values.

## Audit Order

1. CSS variables in `frontend/index.html`
2. Repeated literals in `frontend/index.html`
3. Inline styles in component render methods
4. New component-specific CSS or HTML structure

## Flag By Default

- New hex colors or `rgba(...)` values that do not map to existing variables
- New `border-radius` values that do not align with the current small, medium, pill pattern
- New box shadows for a single surface only
- New spacing values that create a unique rhythm for one component
- Mixed typography treatments for the same UI role

## Current Literal Hotspots

These values already repeat enough to deserve scrutiny:

- radius family: `8px`, `10px`, `12px`, `16px`, `18px`, `99px`, `999px`
- shadow family:
  - `0 10px 25px rgba(24, 29, 58, 0.06)`
  - `0 8px 20px rgba(24, 29, 58, 0.1)`
  - `0 12px 30px rgba(24, 29, 58, 0.08)`
  - `0 26px 80px rgba(14, 20, 38, 0.25)`
- core variables:
  - `--bg-0`
  - `--bg-1`
  - `--panel`
  - `--text`
  - `--muted`
  - `--accent`
  - `--accent-2`
  - `--line`

## Approval Rules

- Approve a new literal only if it is:
  - mandated by the design
  - semantically distinct
  - likely to become a named token immediately
- Otherwise:
  - reuse an existing token
  - rename and promote the repeated value
  - or remove the exception
