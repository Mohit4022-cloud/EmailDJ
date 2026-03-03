"""Model selection and cascade sequencing for generation tiers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from email_generation.runtime_policies import real_provider_preference


@dataclass
class ModelSpec:
    tier: int
    provider: str
    model_name: str
    temperature: float
    timeout_seconds: float = 30.0


# ---------------------------------------------------------------------------
# Per-provider configuration helpers (env-driven)
# ---------------------------------------------------------------------------

_PROVIDER_DEFAULTS: dict[str, tuple[str, float, float]] = {
    # provider -> (default_model, default_timeout, default_max_retries)
    "openai": ("gpt-4.1-nano", 30.0, 2),
    "anthropic": ("claude-3-5-haiku-latest", 35.0, 2),
    "groq": ("llama-3.3-70b-versatile", 20.0, 1),
}

_TIER_MODEL_OVERRIDES: dict[int, dict[str, str]] = {
    1: {"openai": "gpt-4o", "anthropic": "claude-opus-4-6", "groq": "llama-3.3-70b-versatile"},
    2: {"openai": "gpt-4.1-nano", "anthropic": "claude-3-5-haiku-latest", "groq": "llama-3.3-70b-versatile"},
    3: {"openai": "gpt-4.1-nano", "anthropic": "claude-3-5-haiku-latest", "groq": "llama-3.3-70b-versatile"},
}


def _provider_timeout(provider: str) -> float:
    """Per-provider HTTP timeout in seconds, read from env."""
    env_key = f"EMAILDJ_TIMEOUT_{provider.upper()}_SECONDS"
    raw = os.environ.get(env_key, "").strip()
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    return _PROVIDER_DEFAULTS.get(provider, ("", 30.0, 2))[1]


def _provider_max_retries(provider: str) -> int:
    """Max retry attempts per provider, read from env."""
    env_key = f"EMAILDJ_CASCADE_MAX_RETRIES_{provider.upper()}"
    raw = os.environ.get(env_key, "").strip()
    try:
        value = int(raw)
        if value >= 1:
            return value
    except ValueError:
        pass
    return int(_PROVIDER_DEFAULTS.get(provider, ("", 30.0, 2))[2])


def _preferred_provider_order() -> list[str]:
    """Return providers in fallback order: preferred first, then others."""
    preferred = real_provider_preference()
    all_providers = ["openai", "anthropic", "groq"]
    ordered = [preferred] + [p for p in all_providers if p != preferred]
    return ordered


def get_model(tier: int, task: str, throttled: bool = False) -> ModelSpec:
    """Return a single ModelSpec for the given tier."""
    creative = {"sequence_draft", "persona_angle", "master_brief"}
    temperature = 0.7 if task in creative else 0.0

    if throttled:
        return ModelSpec(
            tier=3,
            provider="groq",
            model_name="llama-3.3-70b-versatile",
            temperature=temperature,
            timeout_seconds=_provider_timeout("groq"),
        )

    provider_map = _TIER_MODEL_OVERRIDES.get(tier, _TIER_MODEL_OVERRIDES[2])
    preferred = real_provider_preference()
    provider = preferred if preferred in provider_map else "openai"
    model_name = provider_map[provider]

    return ModelSpec(
        tier=tier,
        provider=provider,
        model_name=model_name,
        temperature=temperature,
        timeout_seconds=_provider_timeout(provider),
    )


def get_cascade_sequence(task: str, throttled: bool = False) -> list[ModelSpec]:
    """Return an ordered list of ModelSpecs to try, primary first.

    If throttled: Groq-only (no cascade, as cost ceiling was exceeded).
    Otherwise: preferred provider first, then fallbacks in order.
    """
    creative = {"sequence_draft", "persona_angle", "master_brief"}
    temperature = 0.7 if task in creative else 0.0

    if throttled:
        return [
            ModelSpec(
                tier=3,
                provider="groq",
                model_name="llama-3.3-70b-versatile",
                temperature=temperature,
                timeout_seconds=_provider_timeout("groq"),
            )
        ]

    providers = _preferred_provider_order()
    sequence: list[ModelSpec] = []
    for idx, provider in enumerate(providers):
        tier = 2 if idx == 0 else 3  # primary gets Tier 2; fallbacks get Tier 3
        model_name = _TIER_MODEL_OVERRIDES.get(tier, _TIER_MODEL_OVERRIDES[2]).get(provider, "llama-3.3-70b-versatile")
        sequence.append(
            ModelSpec(
                tier=tier,
                provider=provider,
                model_name=model_name,
                temperature=temperature,
                timeout_seconds=_provider_timeout(provider),
            )
        )
    return sequence
