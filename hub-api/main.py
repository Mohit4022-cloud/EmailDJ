"""EmailDJ Hub API app factory."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover

    def load_dotenv():
        return None

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware.beta_access import WebBetaAccessMiddleware
from api.middleware.cost_guard import CostGuardMiddleware
from api.middleware.pii_redaction import PiiRedactionMiddleware
from api.routes.assignments import router as assignments_router
from api.routes.campaigns import router as campaigns_router
from api.routes.context_vault import router as context_vault_router
from api.routes.deep_research import router as deep_research_router
from api.routes.quick_generate import router as quick_generate_router
from api.routes.web_mvp import router as web_mvp_router
from api.routes.webhooks import router as webhooks_router
from infra.db import init_engine, shutdown_engine
from infra.redis_client import close_redis, get_redis

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))

REQUIRED_ENV_VARS = ["CHROME_EXTENSION_ORIGIN"]


def _validate_env() -> None:
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_dotenv()
    _validate_env()
    init_engine()
    redis = get_redis()
    await redis.ping()
    try:
        yield
    finally:
        await close_redis()
        await shutdown_engine()


app = FastAPI(title="EmailDJ Hub API", version="0.1.0", lifespan=lifespan)

chrome_origin = os.environ.get("CHROME_EXTENSION_ORIGIN", "")
allow_origins = [
    "http://localhost",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]
if chrome_origin:
    allow_origins.append(chrome_origin)
web_origin = os.environ.get("WEB_APP_ORIGIN", "http://localhost:5174")
if web_origin:
    for origin in web_origin.split(","):
        candidate = origin.strip()
        if candidate:
            allow_origins.append(candidate)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Cost guard runs before handlers; PII redaction scrubs request payloads seen by handlers.
app.add_middleware(WebBetaAccessMiddleware)
app.add_middleware(PiiRedactionMiddleware)
app.add_middleware(CostGuardMiddleware)

app.include_router(quick_generate_router, prefix="/generate", tags=["generate"])
app.include_router(deep_research_router, prefix="/research", tags=["research"])
app.include_router(web_mvp_router, prefix="/web/v1", tags=["web-mvp"])
app.include_router(campaigns_router, prefix="/campaigns", tags=["campaigns"])
app.include_router(assignments_router, prefix="/assignments", tags=["assignments"])
app.include_router(context_vault_router, prefix="/vault", tags=["vault"])
app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])


@app.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}
