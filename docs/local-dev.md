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
3. `npm run check:syntax`
4. `npm run build`
5. Load `dist/` in Chrome Extensions (Developer Mode).

## Full quality-gate command
From `/Users/mohit/EmailDJ/hub-api`:
- `./scripts/checks.sh`

## Quick smoke test
1. Open Salesforce record page.
2. Verify side panel receives `PAYLOAD_READY`.
3. Click `Generate Email`.
4. Confirm token stream appears in editor and `emailComplete` state is reached.
