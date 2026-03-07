# Verification Checklist

Use this checklist for the final UI pass.

## Keyboard

- Can the user reach the main action without tabbing through noise?
- Is tab order aligned with visual order?
- Are modal, dialog, and drawer focus traps correct?
- Is focus returned after closing overlays?

## Visual Accessibility

- Are focus rings obvious on buttons, inputs, sliders, and preset controls?
- Do muted labels and meta text still meet practical contrast needs?
- Are loading, disabled, success, and error states visually distinct?

## Responsive Behavior

- Does the primary task remain obvious on narrow screens?
- Do action rows wrap cleanly?
- Do modal and panel layouts avoid clipped content or overflow?
- Does the editor remain usable on mobile widths?

## Stability And Performance

- Any console errors during generate, remix, modal open, and copy flows?
- Any layout shift when runtime status or draft metadata changes?
- Any sluggish response when sliders update or preset previews load?
- Any avoidable heavy repaint or animation jank?

## Fallback Reporting

If browser tooling is unavailable, say so explicitly and separate:

- checks completed locally
- checks inferred from static inspection
- checks still unverified
