# EmailDJ MVP 0.5 Port List

## Copy As-Is
- `frontend/src/components/SliderBoard.js`
- `frontend/src/components/EmailEditor.js`
- `frontend/src/streamContract.js`
- `frontend/src/utils.js`
- `frontend/src/data/sdrPresets.js`
- `backend/app/sse.py` (adapted from existing SSE wrapper)

## Copy + Adapt
- `frontend/src/main.js`
  - Added AI enrichment buttons, refresh metadata, sources dropdown hookup, and session-aware preset previews.
- `frontend/src/api/client.js`
  - Added enrichment endpoints and single-preset preview calls.
- `frontend/src/components/SDRPresetLibrary.js`
  - Selected preset renders first, remaining previews run concurrently with cap.
- `backend/app/server.py`
  - Implemented `/web/v1/generate`, `/web/v1/remix`, `/web/v1/preset-preview`, enrichment endpoints, and SSE stream orchestration.
- `backend/app/schemas.py`
  - Added strict blueprint, profile, citation, and debug contracts.
- `backend/app/blueprint.py`
  - Added compile pipeline and manual-override precedence.
- `backend/app/rendering.py`
  - Added render pipeline from blueprint + sliders/preset.
- `backend/app/validators.py`
  - Added deterministic validators + repair/fallback.
- `backend/app/enrichment.py`
  - Added target/prospect/sender enrichment loops with citations and caching.
- `backend/app/tools.py`
  - Added tool-only retrieval and extraction helper functions.
- `backend/app/prompts.py`
  - Added prompt templates + prompt hash/version utility.

## Do Not Copy
- `chrome-extension/`
- Campaign/assignment/webhook subsystems from old backend
- `agents/`, `context_vault/`, `delegation/`
- `evals/`, `reports/`, `debug_runs/`
- hard-coded demo companies/prospects and one-off scripts
