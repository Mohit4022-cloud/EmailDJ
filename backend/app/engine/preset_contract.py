from __future__ import annotations

import re
from typing import Any


LENGTH_KEYS = ("short", "medium", "long")
ASSERTIVENESS_LEVELS = {"low", "medium", "high"}
OPENER_DIRECTNESS_LEVELS = {"soft", "balanced", "direct"}
CTA_PLACEMENT_RULES = {"final_exact"}
PROOF_DENSITY_LEVELS = {"tight", "balanced", "broad"}

WORD_RE = re.compile(r"\b[\w']+\b")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def normalize_length_key(length: str | None) -> str:
    key = str(length or "medium").strip().lower()
    if key in LENGTH_KEYS:
        return key
    return "medium"


def word_count(text: str) -> int:
    return len(WORD_RE.findall(text or ""))


def sentence_count(text: str) -> int:
    parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(str(text or "")) if part.strip()]
    return len(parts)


def merge_output_contracts(base: dict[str, Any] | None, override: dict[str, Any] | None) -> dict[str, Any]:
    base_contract = dict(base or {})
    override_contract = dict(override or {})

    base_lengths = dict(base_contract.get("lengths") or {})
    override_lengths = dict(override_contract.get("lengths") or {})
    merged_lengths: dict[str, Any] = {}
    for key in LENGTH_KEYS:
        merged_lengths[key] = {
            **dict(base_lengths.get(key) or {}),
            **dict(override_lengths.get(key) or {}),
        }

    merged = {
        **base_contract,
        **override_contract,
        "lengths": merged_lengths,
    }
    return merged


def resolve_output_contract(preset: dict[str, Any], *, length: str | None) -> dict[str, Any]:
    contract = dict(preset.get("output_contract") or {})
    length_key = normalize_length_key(length)
    length_contract = dict((contract.get("lengths") or {}).get(length_key) or {})
    return {
        "length": length_key,
        "tone": str(contract.get("tone") or "").strip(),
        "assertiveness": str(contract.get("assertiveness") or "").strip(),
        "opener_directness": str(contract.get("opener_directness") or "").strip(),
        "cta_placement": str(contract.get("cta_placement") or "").strip(),
        "proof_density": str(contract.get("proof_density") or "").strip(),
        "target_word_range": dict(length_contract.get("target_word_range") or {}),
        "hard_word_range": dict(length_contract.get("hard_word_range") or {}),
        "sentence_count_guidance": dict(length_contract.get("sentence_count_guidance") or {}),
    }


def validate_output_contract_definition(contract: Any, *, source: str) -> None:
    if not isinstance(contract, dict):
        raise ValueError(f"preset_invalid_output_contract:{source}")

    tone = str(contract.get("tone") or "").strip()
    if not tone:
        raise ValueError(f"preset_invalid_output_contract_field:{source}:tone")

    assertiveness = str(contract.get("assertiveness") or "").strip().lower()
    if assertiveness not in ASSERTIVENESS_LEVELS:
        raise ValueError(f"preset_invalid_output_contract_field:{source}:assertiveness")

    opener_directness = str(contract.get("opener_directness") or "").strip().lower()
    if opener_directness not in OPENER_DIRECTNESS_LEVELS:
        raise ValueError(f"preset_invalid_output_contract_field:{source}:opener_directness")

    cta_placement = str(contract.get("cta_placement") or "").strip().lower()
    if cta_placement not in CTA_PLACEMENT_RULES:
        raise ValueError(f"preset_invalid_output_contract_field:{source}:cta_placement")

    proof_density = str(contract.get("proof_density") or "").strip().lower()
    if proof_density not in PROOF_DENSITY_LEVELS:
        raise ValueError(f"preset_invalid_output_contract_field:{source}:proof_density")

    lengths = contract.get("lengths")
    if not isinstance(lengths, dict):
        raise ValueError(f"preset_invalid_output_contract_field:{source}:lengths")

    for key in LENGTH_KEYS:
        section = lengths.get(key)
        if not isinstance(section, dict):
            raise ValueError(f"preset_invalid_output_contract_length:{source}:{key}")
        _validate_range(section.get("target_word_range"), source=source, key=f"{key}.target_word_range")
        _validate_range(section.get("hard_word_range"), source=source, key=f"{key}.hard_word_range")
        _validate_sentence_guidance(section.get("sentence_count_guidance"), source=source, key=f"{key}.sentence_count_guidance")


def _validate_range(value: Any, *, source: str, key: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"preset_invalid_output_contract_field:{source}:{key}")
    min_value = value.get("min")
    max_value = value.get("max")
    if not isinstance(min_value, int) or not isinstance(max_value, int) or min_value < 1 or max_value < min_value:
        raise ValueError(f"preset_invalid_output_contract_range:{source}:{key}")


def _validate_sentence_guidance(value: Any, *, source: str, key: str) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"preset_invalid_output_contract_field:{source}:{key}")
    target_min = value.get("target_min")
    target_max = value.get("target_max")
    hard_max = value.get("hard_max")
    if not all(isinstance(item, int) and item >= 1 for item in (target_min, target_max, hard_max)):
        raise ValueError(f"preset_invalid_output_contract_sentence_guidance:{source}:{key}")
    if target_max < target_min or hard_max < target_max:
        raise ValueError(f"preset_invalid_output_contract_sentence_guidance:{source}:{key}")

