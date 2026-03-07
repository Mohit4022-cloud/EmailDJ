"""Centralized OpenAI model and reasoning defaults."""

from __future__ import annotations

import os
from typing import Mapping

DEFAULT_OPENAI_MODEL_ALIAS = "gpt-5-nano"
DEFAULT_OPENAI_MODEL_SNAPSHOT = "gpt-5-nano-2025-08-07"
OPENAI_MODEL_ENV_VAR = "EMAILDJ_OPENAI_MODEL"

OPENAI_REASONING_EFFORT_ENV_VAR = "EMAILDJ_OPENAI_REASONING_EFFORT"
OPENAI_REASONING_EFFORT_ENRICHMENT_ENV_VAR = "EMAILDJ_OPENAI_REASONING_EFFORT_ENRICHMENT"
OPENAI_REASONING_EFFORT_DRAFT_ENV_VAR = "EMAILDJ_OPENAI_REASONING_EFFORT_DRAFT"
ALLOWED_OPENAI_REASONING_EFFORTS = ("minimal", "low", "medium", "high")
DEFAULT_OPENAI_REASONING_EFFORT = "high"
DEFAULT_OPENAI_REASONING_EFFORT_ENRICHMENT = "high"
DEFAULT_OPENAI_REASONING_EFFORT_DRAFT = "low"

_ENRICHMENT_TRANSFORMS = frozenset({"enrichment", "extraction"})
_DRAFT_TRANSFORMS = frozenset({"drafting", "rewrite", "rendering"})


def _env_view(raw_env_vars: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return raw_env_vars if raw_env_vars is not None else os.environ


def default_openai_model(raw_env_vars: Mapping[str, str] | None = None) -> str:
    env = _env_view(raw_env_vars)
    model = env.get(OPENAI_MODEL_ENV_VAR, DEFAULT_OPENAI_MODEL_ALIAS).strip()
    return model or DEFAULT_OPENAI_MODEL_ALIAS


def _resolve_effort(value: str | None, default: str) -> str:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in ALLOWED_OPENAI_REASONING_EFFORTS:
        return normalized
    return default


def _normalize_transform_type(value: str | None) -> str:
    normalized = (value or "").strip().lower()
    if normalized in _DRAFT_TRANSFORMS:
        return "drafting"
    if normalized in _ENRICHMENT_TRANSFORMS:
        return "enrichment"
    return "enrichment"


def openai_reasoning_effort(
    raw_env_vars: Mapping[str, str] | None = None,
    model_name: str | None = None,
    transform_type: str | None = None,
) -> str:
    env = _env_view(raw_env_vars)
    _ = model_name  # Kept for backward compatibility with existing callers.
    global_override = _resolve_effort(
        env.get(OPENAI_REASONING_EFFORT_ENV_VAR),
        DEFAULT_OPENAI_REASONING_EFFORT,
    )
    if OPENAI_REASONING_EFFORT_ENV_VAR in env:
        return global_override

    transform_bucket = _normalize_transform_type(transform_type)
    if transform_bucket == "drafting":
        return _resolve_effort(
            env.get(OPENAI_REASONING_EFFORT_DRAFT_ENV_VAR),
            DEFAULT_OPENAI_REASONING_EFFORT_DRAFT,
        )
    return _resolve_effort(
        env.get(OPENAI_REASONING_EFFORT_ENRICHMENT_ENV_VAR),
        DEFAULT_OPENAI_REASONING_EFFORT_ENRICHMENT,
    )


def openai_supports_temperature_override(model_name: str | None) -> bool:
    """Return whether this OpenAI chat model supports explicit temperature values.

    GPT-5 chat models currently require the default temperature behavior and reject
    explicit temperature values like 0.
    """
    model = (model_name or "").strip().lower()
    if not model:
        return True
    return not model.startswith("gpt-5")
