from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


@dataclass(frozen=True)
class Settings:
    app_env: str
    web_app_origin: str
    beta_keys: set[str]
    web_rate_limit_per_min: int
    log_level: str

    openai_api_key: str
    openai_model: str
    openai_reasoning_high: str
    openai_reasoning_low: str

    serper_api_key: str
    brave_search_api_key: str

    target_ttl_seconds: int
    news_ttl_seconds: int
    contact_ttl_seconds: int
    sender_ttl_seconds: int

    stream_chunk_size: int
    provider_stub_enabled: bool
    llm_drafting_enabled: bool
    debug_prompt: bool


def load_settings() -> Settings:
    beta_raw = os.environ.get("EMAILDJ_WEB_BETA_KEYS", "dev-beta-key")
    beta_keys = {item.strip() for item in beta_raw.split(",") if item.strip()}
    return Settings(
        app_env=os.environ.get("APP_ENV", "local").strip().lower() or "local",
        web_app_origin=os.environ.get("WEB_APP_ORIGIN", "http://localhost:5174").strip() or "http://localhost:5174",
        beta_keys=beta_keys or {"dev-beta-key"},
        web_rate_limit_per_min=_env_int("EMAILDJ_WEB_RATE_LIMIT_PER_MIN", 60, minimum=1, maximum=5000),
        log_level=os.environ.get("LOG_LEVEL", "INFO").strip().upper() or "INFO",
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        openai_model=os.environ.get("EMAILDJ_OPENAI_MODEL", "gpt-5-nano").strip() or "gpt-5-nano",
        openai_reasoning_high=os.environ.get("EMAILDJ_OPENAI_REASONING_EFFORT_HIGH", "high").strip() or "high",
        openai_reasoning_low=os.environ.get("EMAILDJ_OPENAI_REASONING_EFFORT_LOW", "minimal").strip() or "minimal",
        serper_api_key=os.environ.get("SERPER_API_KEY", "").strip(),
        brave_search_api_key=os.environ.get("BRAVE_SEARCH_API_KEY", "").strip(),
        target_ttl_seconds=_env_int("EMAILDJ_CACHE_TARGET_TTL_SECONDS", 7 * 24 * 60 * 60, minimum=60),
        news_ttl_seconds=_env_int("EMAILDJ_CACHE_NEWS_TTL_SECONDS", 24 * 60 * 60, minimum=60),
        contact_ttl_seconds=_env_int("EMAILDJ_CACHE_CONTACT_TTL_SECONDS", 14 * 24 * 60 * 60, minimum=60),
        sender_ttl_seconds=_env_int("EMAILDJ_CACHE_SENDER_TTL_SECONDS", 7 * 24 * 60 * 60, minimum=60),
        stream_chunk_size=_env_int("EMAILDJ_STREAM_CHUNK_SIZE", 48, minimum=8, maximum=256),
        provider_stub_enabled=_env_bool("USE_PROVIDER_STUB", False),
        llm_drafting_enabled=_env_bool("LLM_DRAFTING", False),
        debug_prompt=_env_bool("DEBUG_PROMPT", False),
    )
