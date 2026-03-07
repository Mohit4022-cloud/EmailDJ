from __future__ import annotations

import pytest

from app.engine.budget_planner import plan_budget
from app.engine.presets.registry import load_preset
from app.engine.preset_contract import resolve_output_contract
from app.engine.validators import ValidationIssue, validate_message_atoms


def _brief() -> dict:
    return {
        "hooks": [
            {
                "hook_id": "hook_1",
                "hook_text": "RevOps initiative is timely.",
            }
        ],
        "forbidden_claim_patterns": [],
    }


def _angle() -> dict:
    return {
        "angle_id": "angle_1",
        "angle_type": "problem_led",
        "selected_hook_id": "hook_1",
    }


def _atoms(*, preset_id: str, cta_atom: str = "Open to a quick chat to see if this is relevant?") -> dict:
    contract = resolve_output_contract(load_preset(preset_id), length="short")
    budget_plan = plan_budget(
        preset_id=preset_id,
        preset_contract=contract,
        selected_angle=_angle(),
        message_atoms={
            "opener_atom": "Noticed your RevOps scope is tightening workflow consistency.",
            "value_atom": "Teams usually reduce sequence drift when execution is easier to inspect.",
            "proof_atom": "A SaaS team improved reply quality after tightening QA review loops.",
            "cta_atom": cta_atom,
        },
    )
    return {
        "version": "1",
        "preset_id": preset_id,
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "opener_atom": "Noticed your RevOps scope is tightening workflow consistency.",
        "value_atom": "Teams usually reduce sequence drift when execution is easier to inspect.",
        "proof_atom": "A SaaS team improved reply quality after tightening QA review loops.",
        "cta_atom": cta_atom,
        "cta_intent": "Ask whether a quick chat is relevant.",
        "required_cta_line": "Open to a quick chat to see if this is relevant?",
        "target_word_budget": int(budget_plan["target_total_words"]),
        "target_sentence_budget": int(budget_plan["target_sentence_count"]),
    }


def test_budget_planner_derives_stable_target_ranges_from_contract_and_length_tier() -> None:
    direct_contract = resolve_output_contract(load_preset("direct"), length="short")
    challenger_contract = resolve_output_contract(load_preset("challenger"), length="short")
    storyteller_contract = resolve_output_contract(load_preset("storyteller"), length="short")

    direct_plan = plan_budget(preset_id="direct", preset_contract=direct_contract, selected_angle=_angle())
    challenger_plan = plan_budget(preset_id="challenger", preset_contract=challenger_contract, selected_angle=_angle())
    storyteller_plan = plan_budget(preset_id="storyteller", preset_contract=storyteller_contract, selected_angle=_angle())

    assert direct_plan["target_total_words"] == 51
    assert direct_plan["allowed_min_words"] == 40
    assert direct_plan["allowed_max_words"] == 72
    assert challenger_plan["target_total_words"] == 61
    assert challenger_plan["allowed_min_words"] == 46
    assert challenger_plan["allowed_max_words"] == 88
    assert storyteller_plan["target_total_words"] == 60
    assert storyteller_plan["allowed_min_words"] == 46
    assert storyteller_plan["allowed_max_words"] == 86


def test_message_atoms_validator_catches_cta_mismatch_deterministically() -> None:
    contract = resolve_output_contract(load_preset("challenger"), length="short")
    budget_plan = plan_budget(preset_id="challenger", preset_contract=contract, selected_angle=_angle())
    bad_atoms = _atoms(preset_id="challenger", cta_atom="Would you be open to a call next week?")

    with pytest.raises(ValidationIssue) as exc_info:
        validate_message_atoms(
            bad_atoms,
            preset_id="challenger",
            cta_final_line="Open to a quick chat to see if this is relevant?",
            messaging_brief=_brief(),
            selected_angle=_angle(),
            preset_contract=contract,
            forbidden_patterns=[],
            budget_plan=budget_plan,
        )

    assert "atoms_cta_mismatch" in exc_info.value.codes


def test_budget_planner_uses_atom_count_for_sentence_budget() -> None:
    contract = resolve_output_contract(load_preset("storyteller"), length="short")
    plan = plan_budget(
        preset_id="storyteller",
        preset_contract=contract,
        selected_angle=_angle(),
        message_atoms={
            "opener_atom": "Noticed the RevOps work seems focused on keeping handoffs cleaner.",
            "value_atom": "That usually matters when teams are trying to protect meeting quality without adding review drag.",
            "proof_atom": "",
            "cta_atom": "Open to a quick chat to see if this is relevant?",
        },
    )

    assert plan["target_sentence_count"] == 3
    assert plan["feasibility_status"] == "soft_under_target"
