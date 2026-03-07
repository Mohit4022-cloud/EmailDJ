---
name: component-story-writer
description: Keep reusable EmailDJ UI components state-complete and documented. Use when adding or changing reusable frontend primitives so stories and tests cover default, hover, focus, disabled, loading, error, and empty states. If Storybook is not installed, define the story matrix and update tests instead of skipping the work.
---

# Component Story Writer

## Overview

Treat reusable UI components as product surface area, not implementation scraps. Every reusable component should have a state matrix, and story coverage should land with the component once Storybook exists.

## Workflow

1. Decide whether the touched UI is truly reusable:
   - shared primitive or pattern
   - repeated in multiple places
   - likely to be reused after the current task
2. Inspect the current component and tests:
   - `frontend/src/components/*.js`
   - `frontend/tests/*.test.js`
3. Define the minimum state matrix:
   - default
   - hover
   - focus
   - disabled
   - loading
   - error
   - empty
4. If Storybook or Storybook MCP is available, create or update stories.
5. If Storybook is absent, do not skip the work. Produce the story plan, note the missing setup, and update tests or test plans alongside the component.
6. If the component introduces styling primitives, route the result through `$design-system-guardian`.

## Repo Rules

- Current likely reusable targets:
  - `EmailEditor`
  - `SliderBoard`
  - `SDRPresetLibrary`
  - runtime/status badges
  - grouped form-field patterns
- Do not treat page-only layout glue as a reusable component without a reason.
- A component change is incomplete if its important states are undocumented or untested.

## Output

Return these headings when doing story planning or review:

- `reusable_components`
- `required_states`
- `story_or_test_updates`

## Commands

```bash
find frontend/src/components -maxdepth 1 -type f | sort
find frontend/tests -maxdepth 1 -type f | sort
npm --prefix frontend test
```
