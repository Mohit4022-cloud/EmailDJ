"""
EmailDJ Hub API — FastAPI app factory.

IMPLEMENTATION INSTRUCTIONS:
1. Import FastAPI, CORSMiddleware, and all routers from api/routes/*.
2. Create FastAPI app with title="EmailDJ Hub API", version="0.1.0".
3. Add CORSMiddleware — allow origin from env var CHROME_EXTENSION_ORIGIN
   (chrome-extension://...) plus http://localhost for dev. Allow methods=["*"],
   headers=["*"].
4. Add PiiRedactionMiddleware from api/middleware/pii_redaction.py (runs BEFORE
   route handlers on every POST request body).
5. Add CostGuardMiddleware from api/middleware/cost_guard.py.
6. Mount all routers with prefixes:
   - quick_generate router → /generate
   - deep_research router → /research
   - campaigns router → /campaigns
   - assignments router → /assignments
   - context_vault router → /vault
   - webhooks router → /webhooks
7. Set LANGCHAIN_TRACING_V2=true in env / load via python-dotenv at startup.
8. Add a root health check: GET / → {"status": "ok", "version": "0.1.0"}.
9. Configure SSE via sse-starlette (no extra setup needed; routes handle it).
10. Use lifespan context manager to initialize Redis connection pool on startup
    and close on shutdown.
"""

from fastapi import FastAPI

# TODO: implement per instructions above
app = FastAPI(title="EmailDJ Hub API", version="0.1.0")


@app.get("/")
async def health():
    # TODO: return real status including Redis connectivity check
    return {"status": "ok", "version": "0.1.0"}
