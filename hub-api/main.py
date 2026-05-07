"""EmailDJ Hub API app factory."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlparse

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
    ALLOWED_LAUNCH_MODES,
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
    route_gate_sources,
    route_gates,
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
_LOCAL_WEB_ORIGIN_HOSTS = {"localhost", "127.0.0.1"}
_LOCAL_INFRA_HOSTS = {"localhost", "127.0.0.1", "::1"}
_LAUNCH_MODES_REQUIRING_DURABLE_REDIS = {"limited_rollout", "broad_launch"}
_LOCAL_WEB_ALLOW_ORIGINS = [
    "http://localhost",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]


def _quick_mode() -> str:
    return quick_generate_mode()


def _real_provider() -> str:
    return real_provider_preference()


def _preview_pipeline_enabled() -> bool:
    return preview_pipeline_enabled()


def _split_csv_env(raw_value: str) -> list[str]:
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def _configured_web_origins() -> list[str]:
    return _split_csv_env((os.environ.get("WEB_APP_ORIGIN") or "").strip())


def _origin_hostname(origin: str) -> str:
    return (urlparse(origin).hostname or "").strip().lower()


def _origins_are_local_only(origins: list[str]) -> bool:
    return bool(origins) and all(_origin_hostname(origin) in _LOCAL_WEB_ORIGIN_HOSTS for origin in origins)


def _require_safe_production_web_contract(app_env: str) -> None:
    if not is_production_like_environment(app_env):
        return

    web_origins = _configured_web_origins()
    if not web_origins:
        raise RuntimeError("Production-like environments require explicit WEB_APP_ORIGIN.")
    if _origins_are_local_only(web_origins):
        raise RuntimeError("Production-like environments require WEB_APP_ORIGIN to point to deployed web origin(s), not localhost.")

    beta_raw = (os.environ.get("EMAILDJ_WEB_BETA_KEYS") or "").strip()
    if not beta_raw:
        raise RuntimeError("Production-like environments require explicit EMAILDJ_WEB_BETA_KEYS.")
    beta_keys = {part.strip() for part in beta_raw.split(",") if part.strip()}
    if not beta_keys or "dev-beta-key" in beta_keys:
        raise RuntimeError("Production-like environments require EMAILDJ_WEB_BETA_KEYS without dev-beta-key.")

    rate_limit_raw = (os.environ.get("EMAILDJ_WEB_RATE_LIMIT_PER_MIN") or "").strip()
    if not rate_limit_raw:
        raise RuntimeError("Production-like environments require explicit EMAILDJ_WEB_RATE_LIMIT_PER_MIN.")
    try:
        rate_limit = int(rate_limit_raw)
    except ValueError as exc:
        raise RuntimeError("EMAILDJ_WEB_RATE_LIMIT_PER_MIN must be a positive integer.") from exc
    if rate_limit < 1:
        raise RuntimeError("EMAILDJ_WEB_RATE_LIMIT_PER_MIN must be a positive integer.")


def _require_pinned_launch_surfaces(launch_mode: str) -> None:
    if launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        return

    chrome_origin = (os.environ.get("CHROME_EXTENSION_ORIGIN") or "").strip()
    if not chrome_origin or chrome_origin == "chrome-extension://dev":
        raise RuntimeError(
            f"{launch_mode} requires pinned CHROME_EXTENSION_ORIGIN; "
            "replace chrome-extension://dev with the deployed extension origin."
        )

    web_origins = _configured_web_origins()
    if not web_origins:
        raise RuntimeError(f"{launch_mode} requires explicit WEB_APP_ORIGIN.")
    if _origins_are_local_only(web_origins):
        raise RuntimeError(f"{launch_mode} requires WEB_APP_ORIGIN to point to deployed web origin(s), not localhost.")

    beta_raw = (os.environ.get("EMAILDJ_WEB_BETA_KEYS") or "").strip()
    beta_keys = {part.strip() for part in beta_raw.split(",") if part.strip()}
    if not beta_keys or "dev-beta-key" in beta_keys:
        raise RuntimeError(f"{launch_mode} requires explicit EMAILDJ_WEB_BETA_KEYS without dev-beta-key.")

    rate_limit_raw = (os.environ.get("EMAILDJ_WEB_RATE_LIMIT_PER_MIN") or "").strip()
    if not rate_limit_raw:
        raise RuntimeError(f"{launch_mode} requires explicit EMAILDJ_WEB_RATE_LIMIT_PER_MIN.")
    try:
        rate_limit = int(rate_limit_raw)
    except ValueError as exc:
        raise RuntimeError("EMAILDJ_WEB_RATE_LIMIT_PER_MIN must be a positive integer.") from exc
    if rate_limit < 1:
        raise RuntimeError("EMAILDJ_WEB_RATE_LIMIT_PER_MIN must be a positive integer.")


def _redis_url_is_external(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").strip().lower()
    return parsed.scheme in {"redis", "rediss"} and bool(host) and host not in _LOCAL_INFRA_HOSTS


def _database_url_is_external_postgres(raw_url: str) -> bool:
    parsed = urlparse(raw_url)
    host = (parsed.hostname or "").strip().lower()
    scheme = (parsed.scheme or "").strip().lower()
    return scheme.startswith("postgres") and bool(host) and host not in _LOCAL_INFRA_HOSTS


def _require_durable_redis_for_launch(launch_mode: str) -> None:
    if launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        return

    if (os.environ.get("REDIS_FORCE_INMEMORY") or "").strip() == "1":
        raise RuntimeError(
            f"{launch_mode} requires managed Redis; unset REDIS_FORCE_INMEMORY "
            "and set REDIS_URL to a non-local redis/rediss URL."
        )

    redis_url = (os.environ.get("REDIS_URL") or "").strip()
    if not redis_url:
        raise RuntimeError(f"{launch_mode} requires managed Redis; set REDIS_URL to a non-local redis/rediss URL.")
    if not _redis_url_is_external(redis_url):
        raise RuntimeError(f"{launch_mode} requires managed Redis; REDIS_URL must use a non-local redis/rediss host.")


def _require_durable_database_for_launch(launch_mode: str) -> None:
    if launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        return

    database_url = (os.environ.get("DATABASE_URL") or "").strip()
    if not database_url:
        raise RuntimeError(f"{launch_mode} requires managed Postgres; set DATABASE_URL to a non-local Postgres URL.")
    if not _database_url_is_external_postgres(database_url):
        raise RuntimeError(f"{launch_mode} requires managed Postgres; DATABASE_URL must use a non-local Postgres host.")


def _require_real_runtime_for_launch(policies: object) -> None:
    launch_mode = getattr(policies, "launch_mode", "")
    if launch_mode not in _LAUNCH_MODES_REQUIRING_DURABLE_REDIS:
        return

    if bool(getattr(policies, "provider_stub_enabled", False)):
        raise RuntimeError(f"{launch_mode} requires real provider mode; set {PROVIDER_STUB_ENV_VAR}=0.")

    route_gates = dict(getattr(policies, "route_gates", {}) or {})
    if launch_mode == "limited_rollout" and route_gates.get("preview") is True:
        raise RuntimeError(
            "limited_rollout requires preview route disabled; unset EMAILDJ_ROUTE_PREVIEW_ENABLED "
            "or set it to 0."
        )


def _cors_allow_origins() -> list[str]:
    policies = resolve_runtime_policies()
    allow_origins: list[str] = []
    if not is_production_like_environment(policies.app_env):
        allow_origins.extend(_LOCAL_WEB_ALLOW_ORIGINS)

    chrome_origin = (os.environ.get("CHROME_EXTENSION_ORIGIN") or "").strip()
    if chrome_origin:
        allow_origins.append(chrome_origin)

    allow_origins.extend(_configured_web_origins())

    deduped: list[str] = []
    seen: set[str] = set()
    for origin in allow_origins:
        if not origin or origin in seen:
            continue
        seen.add(origin)
        deduped.append(origin)
    return deduped


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
        "launch_mode": policies.launch_mode,
        "route_gates": dict(policies.route_gates),
        "route_gate_sources": dict(policies.route_gate_sources),
        "quick_generate_cascade": cascade_models,
        "strict_lock_enforcement_level": strict_lock_enforcement_level(),
        "repair_loop_enabled": repair_loop_enabled(),
        "debug_success_sample_rate": debug_success_sample_rate(),
        "preview_pipeline_enabled": _preview_pipeline_enabled(),
        "dev_allow_p0_off": policies.dev_allow_p0_off,
        "p0_flags_effective": policies.p0_flags_effective,
        "p0_all_enabled": policies.p0_all_enabled,
        "openai_model_default": default_model,
        "openai_reasoning_effort_enrichment_effective": openai_reasoning_effort(transform_type="enrichment"),
        "openai_reasoning_effort_draft_effective": openai_reasoning_effort(transform_type="drafting"),
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

    configured_launch_mode = (os.environ.get("EMAILDJ_LAUNCH_MODE") or "").strip().lower()
    if configured_launch_mode and configured_launch_mode not in ALLOWED_LAUNCH_MODES:
        raise RuntimeError(
            "Invalid EMAILDJ_LAUNCH_MODE. Expected one of: "
            + ", ".join(sorted(ALLOWED_LAUNCH_MODES))
        )

    policies = resolve_runtime_policies()
    mode = policies.quick_generate_mode
    provider = policies.real_provider_preference
    _require_safe_production_web_contract(policies.app_env)
    _require_pinned_launch_surfaces(policies.launch_mode)
    _require_durable_redis_for_launch(policies.launch_mode)
    _require_durable_database_for_launch(policies.launch_mode)
    _require_real_runtime_for_launch(policies)
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
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
        "launch_mode": policies.launch_mode,
        "route_gates": route_gates(),
        "route_gate_sources": route_gate_sources(),
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
