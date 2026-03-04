"""Centralized OpenAI model and reasoning defaults."""

from __future__ import annotations

import os
from typing import Mapping

DEFAULT_OPENAI_MODEL_ALIAS = "gpt-5-nano"
DEFAULT_OPENAI_MODEL_SNAPSHOT = "gpt-5-nano-2025-08-07"
OPENAI_MODEL_ENV_VAR = "EMAILDJ_OPENAI_MODEL"

OPENAI_REASONING_EFFORT_ENV_VAR = "EMAILDJ_OPENAI_REASONING_EFFORT"
ALLOWED_OPENAI_REASONING_EFFORTS = ("minimal", "low", "medium", "high")
DEFAULT_OPENAI_REASONING_EFFORT = "high"


def _env_view(raw_env_vars: Mapping[str, str] | None = None) -> Mapping[str, str]:
    return raw_env_vars if raw_env_vars is not None else os.environ


def default_openai_model(raw_env_vars: Mapping[str, str] | None = None) -> str:
    env = _env_view(raw_env_vars)
    model = env.get(OPENAI_MODEL_ENV_VAR, DEFAULT_OPENAI_MODEL_ALIAS).strip()
    return model or DEFAULT_OPENAI_MODEL_ALIAS


def openai_reasoning_effort(raw_env_vars: Mapping[str, str] | None = None) -> str:
    env = _env_view(raw_env_vars)
    value = env.get(OPENAI_REASONING_EFFORT_ENV_VAR, DEFAULT_OPENAI_REASONING_EFFORT).strip().lower()
    if value in ALLOWED_OPENAI_REASONING_EFFORTS:
        return value
    return DEFAULT_OPENAI_REASONING_EFFORT
