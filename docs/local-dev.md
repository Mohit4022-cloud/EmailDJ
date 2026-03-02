# EmailDJ Local Dev Runbook

## Hub API
1. `cd /Users/mohit/EmailDJ/hub-api`
2. Create `.env` with at least:
   - `CHROME_EXTENSION_ORIGIN=chrome-extension://<extension-id>`
   - `REDIS_URL=redis://localhost:6379/0`
   - `DATABASE_URL=sqlite+aiosqlite:///./emaildj.db`
   - `EMAILDJ_QUICK_GENERATE_MODE=mock`
3. Create venv + install:
   - `python3 -m venv .venv`
   - `source .venv/bin/activate`
   - `pip install -r requirements.txt`
4. Start Redis locally (or run with in-memory fallback for local-only).
5. Run: `uvicorn main:app --reload`

## Chrome extension
1. `cd /Users/mohit/EmailDJ/chrome-extension`
2. `npm install`
3. `npm test`
4. `npm run check:syntax`
5. `npm run build`
6. Load `dist/` in Chrome Extensions (Developer Mode).

## Execution matrix

1. Extension unit tests:
   - Command: `cd /Users/mohit/EmailDJ/chrome-extension && npm test`
   - Pass criteria: all tests pass, no uncaught runtime errors.
2. Extension static/build checks:
   - Command: `cd /Users/mohit/EmailDJ/chrome-extension && npm run check:syntax && npm run build`
   - Pass criteria: syntax command exits 0; Vite build completes with no fatal errors.
3. Backend targeted quality checks:
   - Command: `cd /Users/mohit/EmailDJ/hub-api && source .venv/bin/activate && pytest -q tests`
   - Pass criteria: pytest suite passes (warnings are tracked separately).
4. Full quality gate:
   - Command: `cd /Users/mohit/EmailDJ/hub-api && source .venv/bin/activate && ./scripts/checks.sh`
   - Pass criteria: all required steps pass (`python compile`, `pytest`, `openapi`, extension syntax/build, mock smoke, lock eval smoke, parity gate, adversarial suite, fail-fast real-mode validation). Credentialed real-mode smoke runs only when `EMAILDJ_RUN_REAL_MODE_SMOKE=1`.

## Quick smoke test
1. Open Salesforce record page.
2. Verify side panel receives `PAYLOAD_READY`.
3. Click `Generate Email`.
4. Confirm token stream appears in editor and `emailComplete` state is reached.

## Web app MVP
1. `cd /Users/mohit/EmailDJ/web-app`
2. `npm install`
3. `npm test`
4. `npm run check:syntax`
5. `npm run dev`
6. Open `http://localhost:5174` and set beta key (`dev-beta-key` by default).

## Web MVP smoke test
1. Ensure Hub API is running with:
   - `WEB_APP_ORIGIN=http://localhost:5174`
   - `EMAILDJ_WEB_BETA_KEYS=dev-beta-key`
2. In web app, fill prospect fields and paste research text (>=20 chars).
3. Click `Generate` and verify streamed draft appears.
4. Move sliders and verify remix runs automatically after short debounce.
5. Click `Save Remix` and verify draft copies to clipboard.
