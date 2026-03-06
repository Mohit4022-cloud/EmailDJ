from __future__ import annotations

from app.engine.preset_contract import resolve_output_contract
from app.engine.presets import load_preset


def test_preset_contract_resolves_length_specific_fields() -> None:
    preset = load_preset("challenger")

    contract = resolve_output_contract(preset, length="short")

    assert contract["length"] == "short"
    assert contract["assertiveness"] == "high"
    assert contract["opener_directness"] == "direct"
    assert contract["cta_placement"] == "final_exact"
    assert contract["proof_density"] == "tight"
    assert contract["target_word_range"] == {"min": 52, "max": 78}
    assert contract["hard_word_range"] == {"min": 46, "max": 88}
    assert contract["sentence_count_guidance"] == {"target_min": 3, "target_max": 4, "hard_max": 5}


def test_preset_contract_merges_base_defaults() -> None:
    preset = load_preset("direct")

    contract = resolve_output_contract(preset, length="medium")

    assert contract["length"] == "medium"
    assert contract["cta_placement"] == "final_exact"
    assert contract["tone"] == "confident and concise"
    assert contract["hard_word_range"]["max"] >= contract["target_word_range"]["max"]
