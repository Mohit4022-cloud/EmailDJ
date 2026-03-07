"""Runtime policy helpers for compliance enforcement and debug sampling."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Mapping

ALLOWED_ENFORCEMENT_LEVELS = ("warn", "repair", "block")
ALLOWED_QUICK_GENERATE_MODES = ("mock", "real")
ALLOWED_REAL_PROVIDERS = ("openai", "anthropic", "groq")
ALLOWED_LAUNCH_MODES = ("dev", "limited_rollout", "broad_launch")

DEV_ENVIRONMENTS = {"local", "dev", "development"}
PROD_ENVIRONMENTS = {"staging", "prod", "production"}
TEST_ENVIRONMENTS = {"test"}

P0_FEATURE_FLAGS = (
    "FEATURE_PERSONA_ROUTER",
    "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL",
    "FEATURE_PRESET_TRUE_REWRITE",
    "FEATURE_STRUCTURED_OUTPUT",
    "FEATURE_SENTENCE_SAFE_TRUNCATION",
    "FEATURE_LOSSLESS_STREAMING",
    "FEATURE_FLUENCY_REPAIR",
)

PROVIDER_STUB_ENV_VAR = "USE_PROVIDER_STUB"
DEV_ALLOW_P0_OFF_ENV_VAR = "DEV_ALLOW_P0_OFF"

_FEATURE_DEFAULTS: dict[str, bool] = {
    "FEATURE_STRUCTURED_OUTPUT": False,
    "FEATURE_SENTENCE_SAFE_TRUNCATION": False,
    "FEATURE_LOSSLESS_STREAMING": False,
    "FEATURE_FLUENCY_REPAIR": False,
    "FEATURE_SHADOW_MODE": False,
    "FEATURE_PERSONA_ROUTER": False,
    "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL": False,
    "FEATURE_PRESET_TRUE_REWRITE": False,
}

_DEV_FEATURE_DEFAULTS: dict[str, bool] = {
    **_FEATURE_DEFAULTS,
    "FEATURE_STRUCTURED_OUTPUT": True,
    "FEATURE_SENTENCE_SAFE_TRUNCATION": True,
    "FEATURE_LOSSLESS_STREAMING": True,
    "FEATURE_FLUENCY_REPAIR": True,
    "FEATURE_PERSONA_ROUTER": True,
    "FEATURE_NO_PROSPECT_OWNS_GUARDRAIL": True,
    "FEATURE_PRESET_TRUE_REWRITE": True,
}

_ROLLOUT_ENDPOINT: ContextVar[str] = ContextVar("rollout_endpoint", default="")
_ROLLOUT_BUCKET_KEY: ContextVar[str] = ContextVar("rollout_bucket_key", default="")


@dataclass(frozen=True)
class RuntimePolicies:
    app_env: str
    quick_generate_mode: str
    provider_stub_enabled: bool
    real_provider_preference: str
    launch_mode: str
    route_gates: dict[str, bool]
    route_gate_sources: dict[str, str]
    preview_pipeline_enabled: bool
    feature_defaults: dict[str, bool]
    dev_allow_p0_off: bool
    p0_flags_effective: dict[str, bool]
    p0_all_enabled: bool


def _env_view(raw_env_vars: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return raw_env_vars if raw_env_vars is not None else os.environ


def _bool_from_mapping(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def _bool_from_env(name: str, default: bool) -> bool:
    return _bool_from_mapping(_env_view(), name, default)


def _int_from_mapping(
    env: Mapping[str, str],
    name: str,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = env.get(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _int_from_env(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    return _int_from_mapping(_env_view(), name, default, minimum=minimum, maximum=maximum)


def _default_app_env(env: Mapping[str, str]) -> str:
    # Keep tests deterministic while preserving local-dev defaults for real runtime.
    return "test" if env.get("PYTEST_CURRENT_TEST") else "local"


def _normalized_app_env(env: Mapping[str, str]) -> str:
    raw = (env.get("APP_ENV") or _default_app_env(env)).strip().lower()
    return raw or _default_app_env(env)


def is_dev_environment(app_env: str | None = None, raw_env_vars: Mapping[str, str] | None = None) -> bool:
    env_name = (app_env or _normalized_app_env(_env_view(raw_env_vars))).strip().lower()
    return env_name in DEV_ENVIRONMENTS


def is_production_like_environment(app_env: str | None = None, raw_env_vars: Mapping[str, str] | None = None) -> bool:
    env_name = (app_env or _normalized_app_env(_env_view(raw_env_vars))).strip().lower()
    return env_name in PROD_ENVIRONMENTS


def _feature_defaults_for_env(app_env: str) -> dict[str, bool]:
    if app_env in DEV_ENVIRONMENTS:
        return dict(_DEV_FEATURE_DEFAULTS)
    return dict(_FEATURE_DEFAULTS)


def _default_launch_mode(app_env: str) -> str:
    if app_env in DEV_ENVIRONMENTS | TEST_ENVIRONMENTS:
        return "dev"
    return "limited_rollout"


def _route_gate_default(launch_mode: str, route: str) -> bool:
    if launch_mode == "limited_rollout" and route == "preview":
        return False
    return True


def _resolve_route_gates(env: Mapping[str, str], *, launch_mode: str) -> tuple[dict[str, bool], dict[str, str]]:
    route_env_names = {
        "generate": "EMAILDJ_ROUTE_GENERATE_ENABLED",
        "remix": "EMAILDJ_ROUTE_REMIX_ENABLED",
        "preview": "EMAILDJ_ROUTE_PREVIEW_ENABLED",
    }
    route_gates: dict[str, bool] = {}
    route_sources: dict[str, str] = {}
    for route, env_name in route_env_names.items():
        default_enabled = _route_gate_default(launch_mode, route)
        if env_name in env:
            route_gates[route] = _bool_from_mapping(env, env_name, default_enabled)
            route_sources[route] = "explicit_env"
        else:
            route_gates[route] = default_enabled
            route_sources[route] = f"launch_mode:{launch_mode}"
    return route_gates, route_sources


def resolve_runtime_policies(
    env: str | None = None,
    raw_env_vars: Mapping[str, str] | None = None,
) -> RuntimePolicies:
    raw_env = _env_view(raw_env_vars)
    app_env = (env or _normalized_app_env(raw_env)).strip().lower() or _normalized_app_env(raw_env)

    provider_stub_enabled = _bool_from_mapping(raw_env, PROVIDER_STUB_ENV_VAR, False)

    quick_generate_mode = "mock" if provider_stub_enabled else "real"

    provider = (raw_env.get("EMAILDJ_REAL_PROVIDER") or "openai").strip().lower() or "openai"
    if provider not in ALLOWED_REAL_PROVIDERS:
        provider = "openai"

    launch_mode = (raw_env.get("EMAILDJ_LAUNCH_MODE") or _default_launch_mode(app_env)).strip().lower() or _default_launch_mode(app_env)
    if launch_mode not in ALLOWED_LAUNCH_MODES:
        launch_mode = _default_launch_mode(app_env)

    route_gates, route_gate_sources = _resolve_route_gates(raw_env, launch_mode=launch_mode)

    preview_pipeline_default = app_env in DEV_ENVIRONMENTS
    preview_pipeline_enabled = _bool_from_mapping(raw_env, "EMAILDJ_PRESET_PREVIEW_PIPELINE", preview_pipeline_default)

    feature_defaults = _feature_defaults_for_env(app_env)
    dev_allow_p0_off = _bool_from_mapping(raw_env, DEV_ALLOW_P0_OFF_ENV_VAR, False)

    p0_flags_effective: dict[str, bool] = {}
    for feature_name in P0_FEATURE_FLAGS:
        base_default = feature_defaults.get(feature_name, False)
        base_flag = _bool_from_mapping(raw_env, feature_name, base_default)
        global_flag = _bool_from_mapping(raw_env, f"{feature_name}_GLOBAL", base_flag)
        rollout_percent = _int_from_mapping(raw_env, f"{feature_name}_ROLLOUT_PERCENT", default=100, minimum=0, maximum=100)
        allowed_endpoints = _normalized_endpoint_set(raw_env.get(f"{feature_name}_ENDPOINTS"))
        endpoint_allowed = not allowed_endpoints or "generate" in allowed_endpoints
        p0_flags_effective[feature_name] = global_flag and rollout_percent > 0 and endpoint_allowed

    p0_all_enabled = all(p0_flags_effective.get(name, False) for name in P0_FEATURE_FLAGS)

    return RuntimePolicies(
        app_env=app_env,
        quick_generate_mode=quick_generate_mode,
        provider_stub_enabled=provider_stub_enabled,
        real_provider_preference=provider,
        launch_mode=launch_mode,
        route_gates=route_gates,
        route_gate_sources=route_gate_sources,
        preview_pipeline_enabled=preview_pipeline_enabled,
        feature_defaults=feature_defaults,
        dev_allow_p0_off=dev_allow_p0_off,
        p0_flags_effective=p0_flags_effective,
        p0_all_enabled=p0_all_enabled,
    )


def quick_generate_mode() -> str:
    return resolve_runtime_policies().quick_generate_mode


def provider_stub_enabled() -> bool:
    return resolve_runtime_policies().provider_stub_enabled


def real_provider_preference() -> str:
    return resolve_runtime_policies().real_provider_preference


def preview_pipeline_enabled() -> bool:
    return resolve_runtime_policies().preview_pipeline_enabled


def launch_mode() -> str:
    return resolve_runtime_policies().launch_mode


def route_gates() -> dict[str, bool]:
    return dict(resolve_runtime_policies().route_gates)


def route_gate_sources() -> dict[str, str]:
    return dict(resolve_runtime_policies().route_gate_sources)


def route_enabled(route: str) -> bool:
    normalized = (route or "").strip().lower()
    return bool(resolve_runtime_policies().route_gates.get(normalized, True))


def repair_loop_enabled() -> bool:
    return _bool_from_env("EMAILDJ_REPAIR_LOOP_ENABLED", True)


def strict_lock_enforcement_level() -> str:
    level = os.environ.get("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair").strip().lower() or "repair"
    if level in ALLOWED_ENFORCEMENT_LEVELS:
        return level
    return "repair"


def debug_success_sample_rate() -> float:
    raw = os.environ.get("EMAILDJ_DEBUG_SUCCESS_SAMPLE_RATE", "0.01").strip() or "0.01"
    try:
        value = float(raw)
    except ValueError:
        return 0.01
    return max(0.0, min(1.0, value))


def _normalized_endpoint_set(raw: str | None) -> set[str]:
    if not raw:
        return set()
    parts = [entry.strip().lower() for entry in raw.split(",")]
    return {entry for entry in parts if entry}


def _stable_rollout_bucket(feature_name: str, endpoint: str, bucket_key: str) -> int:
    seed = f"{feature_name}:{endpoint}:{bucket_key}".encode("utf-8")
    digest = hashlib.sha256(seed).hexdigest()
    return int(digest[:8], 16) % 100


def _feature_default(feature_name: str) -> bool:
    return bool(resolve_runtime_policies().feature_defaults.get(feature_name, False))


def _feature_rollout_enabled(feature_name: str, default: bool | None = None) -> bool:
    return bool(feature_rollout_details(feature_name, default)["enabled"])


def feature_rollout_details(feature_name: str, default: bool | None = None) -> dict[str, object]:
    endpoint = _ROLLOUT_ENDPOINT.get("").strip().lower()
    bucket_key = _ROLLOUT_BUCKET_KEY.get("").strip()
    feature_default = _feature_default(feature_name) if default is None else default

    base_flag = _bool_from_env(feature_name, feature_default)
    global_flag = _bool_from_env(f"{feature_name}_GLOBAL", base_flag)
    if not global_flag:
        return {
            "feature": feature_name,
            "endpoint": endpoint or "global",
            "bucket_key": bucket_key or "global",
            "base_flag": base_flag,
            "global_flag": global_flag,
            "allowed_endpoints": [],
            "rollout_percent": 0,
            "hashed_bucket": None,
            "enabled": False,
        }

    endpoint_raw = os.environ.get(f"{feature_name}_ENDPOINTS")
    allowed_endpoints = _normalized_endpoint_set(endpoint_raw)
    if allowed_endpoints and endpoint not in allowed_endpoints:
        return {
            "feature": feature_name,
            "endpoint": endpoint or "global",
            "bucket_key": bucket_key or "global",
            "base_flag": base_flag,
            "global_flag": global_flag,
            "allowed_endpoints": sorted(allowed_endpoints),
            "rollout_percent": _int_from_env(f"{feature_name}_ROLLOUT_PERCENT", default=100, minimum=0, maximum=100),
            "hashed_bucket": None,
            "enabled": False,
        }

    rollout_percent = _int_from_env(f"{feature_name}_ROLLOUT_PERCENT", default=100, minimum=0, maximum=100)
    if rollout_percent >= 100:
        return {
            "feature": feature_name,
            "endpoint": endpoint or "global",
            "bucket_key": bucket_key or "global",
            "base_flag": base_flag,
            "global_flag": global_flag,
            "allowed_endpoints": sorted(allowed_endpoints),
            "rollout_percent": rollout_percent,
            "hashed_bucket": None,
            "enabled": True,
        }
    if rollout_percent <= 0:
        return {
            "feature": feature_name,
            "endpoint": endpoint or "global",
            "bucket_key": bucket_key or "global",
            "base_flag": base_flag,
            "global_flag": global_flag,
            "allowed_endpoints": sorted(allowed_endpoints),
            "rollout_percent": rollout_percent,
            "hashed_bucket": None,
            "enabled": False,
        }

    hashed_bucket = _stable_rollout_bucket(feature_name, endpoint=endpoint or "global", bucket_key=bucket_key or "global")
    return {
        "feature": feature_name,
        "endpoint": endpoint or "global",
        "bucket_key": bucket_key or "global",
        "base_flag": base_flag,
        "global_flag": global_flag,
        "allowed_endpoints": sorted(allowed_endpoints),
        "rollout_percent": rollout_percent,
        "hashed_bucket": hashed_bucket,
        "enabled": hashed_bucket < rollout_percent,
    }


def feature_rollout_snapshot() -> dict[str, dict[str, object]]:
    defaults = resolve_runtime_policies().feature_defaults
    return {name: feature_rollout_details(name, defaults.get(name, False)) for name in _FEATURE_DEFAULTS}


def feature_flags_effective() -> dict[str, bool]:
    return {name: bool(info["enabled"]) for name, info in feature_rollout_snapshot().items()}


@contextmanager
def rollout_context(endpoint: str, bucket_key: str):
    endpoint_token = _ROLLOUT_ENDPOINT.set((endpoint or "").strip().lower())
    bucket_token = _ROLLOUT_BUCKET_KEY.set((bucket_key or "").strip())
    try:
        yield
    finally:
        _ROLLOUT_ENDPOINT.reset(endpoint_token)
        _ROLLOUT_BUCKET_KEY.reset(bucket_token)


def feature_structured_output_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_STRUCTURED_OUTPUT")


def feature_sentence_safe_truncation_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_SENTENCE_SAFE_TRUNCATION")


def feature_lossless_streaming_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_LOSSLESS_STREAMING")


def feature_fluency_repair_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_FLUENCY_REPAIR")


def feature_shadow_mode_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_SHADOW_MODE")


def feature_persona_router_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_PERSONA_ROUTER")


def feature_no_prospect_owns_guardrail_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_NO_PROSPECT_OWNS_GUARDRAIL")


def feature_preset_true_rewrite_enabled() -> bool:
    return _feature_rollout_enabled("FEATURE_PRESET_TRUE_REWRITE")


def allowed_facts_target_count() -> int:
    return _int_from_env("EMAILDJ_ALLOWED_FACTS_TARGET_COUNT", default=8, minimum=8, maximum=12)


def web_mvp_stream_chunk_size() -> int:
    return _int_from_env("EMAILDJ_WEB_MVP_STREAM_CHUNK_SIZE", default=48, minimum=8, maximum=512)


def web_mvp_output_token_budget_default() -> int:
    return _int_from_env("EMAILDJ_WEB_MVP_OUTPUT_TOKENS_DEFAULT", default=420, minimum=128, maximum=4096)


def web_mvp_output_token_budget_long() -> int:
    return _int_from_env("EMAILDJ_WEB_MVP_OUTPUT_TOKENS_LONG", default=700, minimum=256, maximum=4096)
