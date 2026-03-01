"""Model selection for generation tiers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ModelSpec:
    tier: int
    provider: str
    model_name: str
    temperature: float


def get_model(tier: int, task: str, throttled: bool = False) -> ModelSpec:
    creative = {"sequence_draft", "persona_angle", "master_brief"}
    temperature = 0.7 if task in creative else 0.0

    if throttled:
        return ModelSpec(tier=3, provider="groq", model_name="llama-3.3-70b-versatile", temperature=temperature)

    if tier == 1:
        return ModelSpec(tier=1, provider="openai", model_name="gpt-4o", temperature=temperature)
    if tier == 2:
        return ModelSpec(tier=2, provider="openai", model_name="gpt-4.1-nano", temperature=temperature)
    return ModelSpec(tier=3, provider="groq", model_name="llama-3.3-70b-versatile", temperature=temperature)
