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

from fastapi import FastAPI, HTTPException, Query
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
from email_generation.model_defaults import default_openai_model, openai_reasoning_effort
from email_generation.model_cascade import get_cascade_sequence
from email_generation.runtime_policies import (
    ALLOWED_QUICK_GENERATE_MODES,
    ALLOWED_REAL_PROVIDERS,
    ALLOWED_ENFORCEMENT_LEVELS,
    DEV_ALLOW_P0_OFF_ENV_VAR,
    P0_FEATURE_FLAGS,
    PROVIDER_STUB_ENV_VAR,
    debug_success_sample_rate,
    feature_flags_effective,
    feature_rollout_snapshot,
    is_dev_environment,
    is_production_like_environment,
    preview_pipeline_enabled,
    quick_generate_mode,
    real_provider_preference,
    repair_loop_enabled,
    resolve_runtime_policies,
    rollout_context,
    strict_lock_enforcement_level,
)
from infra.db import init_engine, shutdown_engine
from infra.redis_client import close_redis, get_redis

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

REQUIRED_ENV_VARS = ["CHROME_EXTENSION_ORIGIN"]
_PROVIDER_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
}


def _quick_mode() -> str:
    return quick_generate_mode()


def _real_provider() -> str:
    return real_provider_preference()


def _preview_pipeline_enabled() -> bool:
    return preview_pipeline_enabled()


def _generation_attestation() -> dict[str, object]:
    policies = resolve_runtime_policies()
    default_model = default_openai_model()
    mode = policies.quick_generate_mode
    provider = policies.real_provider_preference
    cascade = get_cascade_sequence(task="quick_generate", throttled=False)
    cascade_models = [f"{spec.provider}/{spec.model_name}" for spec in cascade]
    return {
        "app_env": policies.app_env,
        "quick_generate_mode": mode,
        "real_provider_preference": provider,
        "provider_stub_enabled": policies.provider_stub_enabled,
        "quick_generate_cascade": cascade_models,
        "strict_lock_enforcement_level": strict_lock_enforcement_level(),
        "repair_loop_enabled": repair_loop_enabled(),
        "debug_success_sample_rate": debug_success_sample_rate(),
        "preview_pipeline_enabled": _preview_pipeline_enabled(),
        "dev_allow_p0_off": policies.dev_allow_p0_off,
        "p0_flags_effective": policies.p0_flags_effective,
        "p0_all_enabled": policies.p0_all_enabled,
        "openai_model_default": default_model,
        "openai_reasoning_effort": openai_reasoning_effort(),
        "preview_extractor_model": os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_EXTRACTOR", default_model).strip() or default_model,
        "preview_generator_model": os.environ.get("EMAILDJ_PRESET_PREVIEW_MODEL_GENERATOR", default_model).strip() or default_model,
    }


def _validate_env() -> None:
    missing = [k for k in REQUIRED_ENV_VARS if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Missing required env vars: {', '.join(missing)}")

    configured_mode = (os.environ.get("EMAILDJ_QUICK_GENERATE_MODE") or "").strip().lower()
    if configured_mode and configured_mode not in ALLOWED_QUICK_GENERATE_MODES:
        raise RuntimeError(
            "Invalid EMAILDJ_QUICK_GENERATE_MODE. Expected one of: "
            + ", ".join(sorted(ALLOWED_QUICK_GENERATE_MODES))
        )

    configured_provider = (os.environ.get("EMAILDJ_REAL_PROVIDER") or "").strip().lower()
    if configured_provider and configured_provider not in ALLOWED_REAL_PROVIDERS:
        raise RuntimeError(
            "Invalid EMAILDJ_REAL_PROVIDER. Expected one of: "
            + ", ".join(sorted(ALLOWED_REAL_PROVIDERS))
        )

    policies = resolve_runtime_policies()
    mode = policies.quick_generate_mode
    provider = policies.real_provider_preference
    if configured_mode == "mock" and not policies.provider_stub_enabled:
        logger.warning(
            "EMAILDJ_QUICK_GENERATE_MODE=mock ignored unless %s=1; continuing in REAL mode.",
            PROVIDER_STUB_ENV_VAR,
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

    if mode == "mock" and not policies.provider_stub_enabled:
        raise RuntimeError(f"Mock mode requires explicit {PROVIDER_STUB_ENV_VAR}=1.")

    if policies.provider_stub_enabled:
        logger.warning(
            "WARNING: PROVIDER STUB ENABLED — REAL AI DISABLED (set %s=0 to restore real mode).",
            PROVIDER_STUB_ENV_VAR,
        )

    if is_production_like_environment(policies.app_env) and mode == "mock":
        logger.warning(
            "EMAILDJ_MOCK_IN_PROD: Running in MOCK mode on '%s' environment — all traffic uses stub output.",
            policies.app_env,
        )

    if is_dev_environment(policies.app_env):
        with rollout_context(endpoint="generate", bucket_key="startup"):
            effective_flags = feature_flags_effective()
        p0_effective = {name: bool(effective_flags.get(name, False)) for name in P0_FEATURE_FLAGS}
        p0_all_enabled = all(p0_effective.values())
        if not p0_all_enabled and not policies.dev_allow_p0_off:
            raise RuntimeError(
                "Dev must run with P0 features enabled. "
                f"Set {DEV_ALLOW_P0_OFF_ENV_VAR}=1 to override."
            )
        if not p0_all_enabled and policies.dev_allow_p0_off:
            logger.warning(
                "DEV_P0_OVERRIDE_ACTIVE: %s=1 with disabled P0 flags %s",
                DEV_ALLOW_P0_OFF_ENV_VAR,
                [name for name, enabled in p0_effective.items() if not enabled],
            )

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
    with rollout_context(endpoint="startup", bucket_key="startup"):
        logger.info("generation_runtime_feature_snapshot", extra={"feature_flags": feature_rollout_snapshot()})
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


@app.get("/debug/config")
async def debug_config(
    endpoint: str = Query(default="generate", pattern="^(generate|remix|preview|stream|startup)$"),
    bucket_key: str = Query(default="debug"),
) -> dict[str, object]:
    policies = resolve_runtime_policies()
    app_env = policies.app_env
    explicit = os.environ.get("EMAILDJ_ENABLE_DEBUG_ENDPOINTS", "0").strip().lower()
    if app_env not in {"local", "dev", "development", "test"} and explicit not in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    from email_generation.preset_preview_pipeline import preview_prompt_template_hashes
    from email_generation.prompt_templates import web_mvp_prompt_template_hash

    with rollout_context(endpoint=endpoint, bucket_key=bucket_key):
        feature_flags = feature_rollout_snapshot()
        effective_flags = feature_flags_effective()
    return {
        "app_env": app_env,
        "runtime_mode": policies.quick_generate_mode,
        "provider_stub_enabled": policies.provider_stub_enabled,
        "real_provider_preference": policies.real_provider_preference,
        "preview_pipeline_enabled": policies.preview_pipeline_enabled,
        "p0_flags_effective": policies.p0_flags_effective,
        "p0_all_enabled": policies.p0_all_enabled,
        "runtime_attestation": _generation_attestation(),
        "feature_flags": feature_flags,
        "effective_flags": effective_flags,
        "feature_env_raw": {key: value for key, value in os.environ.items() if key.startswith("FEATURE_")},
        "prompt_template_versions": {
            "web_mvp_prompt_hash": web_mvp_prompt_template_hash(),
            "preview_prompt_hashes": preview_prompt_template_hashes(),
        },
    }
