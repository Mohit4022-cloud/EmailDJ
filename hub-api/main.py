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
from email_generation.model_cascade import get_cascade_sequence
from email_generation.runtime_policies import (
    ALLOWED_ENFORCEMENT_LEVELS,
    debug_success_sample_rate,
    repair_loop_enabled,
    strict_lock_enforcement_level,
)
from infra.db import init_engine, shutdown_engine
from infra.redis_client import close_redis, get_redis

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = ["CHROME_EXTENSION_ORIGIN"]
_ALLOWED_MODES = {"mock", "real"}
_ALLOWED_PROVIDERS = {"openai", "anthropic", "groq"}
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
}


def _quick_mode() -> str:
    return os.environ.get("EMAILDJ_QUICK_GENERATE_MODE", "mock").strip().lower() or "mock"


def _real_provider() -> str:
    return os.environ.get("EMAILDJ_REAL_PROVIDER", "openai").strip().lower() or "openai"


def _preview_pipeline_enabled() -> bool:
    return os.environ.get("EMAILDJ_PRESET_PREVIEW_PIPELINE", "off").strip().lower() == "on"


def _generation_attestation() -> dict[str, object]:
    mode = _quick_mode()
    provider = _real_provider()
    cascade = get_cascade_sequence(task="quick_generate", throttled=False)
    cascade_models = [f"{spec.provider}/{spec.model_name}" for spec in cascade]
    return {
        "quick_generate_mode": mode,
        "real_provider_preference": provider,
        "quick_generate_cascade": cascade_models,
        "strict_lock_enforcement_level": strict_lock_enforcement_level(),
        "repair_loop_enabled": repair_loop_enabled(),
        "debug_success_sample_rate": debug_success_sample_rate(),
        "preview_pipeline_enabled": _preview_pipeline_enabled(),
        "preview_extractor_model": os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_EXTRACTOR", "gpt-4o-mini").strip() or "gpt-4o-mini",
        "preview_generator_model": os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_GENERATOR", "gpt-4o-mini").strip() or "gpt-4o-mini",
    }


def _validate_env() -> None:
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    mode = _quick_mode()
    if mode not in _ALLOWED_MODES:
        raise RuntimeError(
            "Invalid EMAILDJ_QUICK_GENERATE_MODE. Expected one of: "
            + ", ".join(sorted(_ALLOWED_MODES))
        )

    provider = _real_provider()
    if provider not in _ALLOWED_PROVIDERS:
        raise RuntimeError(
            "Invalid EMAILDJ_REAL_PROVIDER. Expected one of: "
            + ", ".join(sorted(_ALLOWED_PROVIDERS))
        )

    enforcement_level = os.environ.get("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair").strip().lower() or "repair"
    if enforcement_level not in ALLOWED_ENFORCEMENT_LEVELS:
        raise RuntimeError(
            "Invalid EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL. Expected one of: "
            + ", ".join(sorted(ALLOWED_ENFORCEMENT_LEVELS))
        )

    sample_rate_raw = os.environ.get("EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE", "0.01").strip() or "0.01"
    try:
        sample_rate = float(sample_rate_raw)
    except ValueError as exc:
        raise RuntimeError("EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE must be a float between 0 and 1.") from exc
    if sample_rate < 0.0 or sample_rate > 1.0:
        raise RuntimeError("EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE must be between 0 and 1.")

    if mode == "real":
        key_name = _PROVIDER_KEY_ENV[provider]
        if not os.environ.get(key_name):
            raise RuntimeError(
                f"EMAILDJ_QUICK_GENERATE_MODE=real requires {key_name} for provider '{provider}'."
            )
        if _preview_pipeline_enabled() and not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(
                "EMAILDJ_PRESET_PREVIEW_PIPELINE=on with real mode requires OPENAI_API_KEY "
                "(preview pipeline is OpenAI-backed)."
            )


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_dotenv()
    _validate_env()
    logger.info("generation_runtime_attestation", extra=_generation_attestation())
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
