from __future__ import annotations

from app.engine.prompts import stage_a, stage_c, stage_c0


def _messaging_brief() -> dict:
    return {
        "version": "1",
        "brief_id": "brief_1",
        "facts_from_input": [],
        "hooks": [],
    }


def _fit_map() -> dict:
    return {
        "version": "1",
        "hypotheses": [],
    }


def _angle_set() -> dict:
    return {
        "version": "1",
        "angles": [
            {
                "angle_id": "angle_1",
                "value": "Protect forecast consistency",
                "proof": "A SaaS team improved reply quality after tightening QA.",
            }
        ],
    }


def _atoms(*, proof_gap: bool) -> dict:
    return {
        "version": "1",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "opener_line": "Nimbus expanded RevOps ownership in January 2026.",
        "value_line": "RevOps teams cut forecasting variance in one quarter.",
        "proof_line": "" if proof_gap else "A fintech team lifted meetings after sequence QA.",
        "proof_gap": proof_gap,
        "cta_line": "Open to a quick chat to see if this is relevant?",
    }


def test_stage_c0_prompt_contains_value_formula_and_external_proof_rule() -> None:
    messages = stage_c0.build_messages(
        _messaging_brief(),
        _fit_map(),
        _angle_set(),
        "angle_1",
        {"tone": 0.5, "framing": 0.5, "stance": 0.5, "length": "short"},
        "Open to a quick chat to see if this is relevant?",
    )
    user_prompt = messages[1]["content"]

    assert "value_line formula (use this structure exactly)" in user_prompt
    assert "[Persona's team] [specific verb: cut/reduced/protected/freed]" in user_prompt
    assert "If no brief proof point supports this formula, set proof_line to empty string \"\"." in user_prompt
    assert "never use the prospect's own facts as proof" in user_prompt


def test_stage_a_prompt_contains_containment_rejection_rules() -> None:
    messages = stage_a.build_messages(
        {
            "user_company": {
                "product_summary": "Workflow QA Platform",
                "icp_description": "RevOps teams",
                "differentiators": [],
                "proof_points": [],
                "do_not_say": [],
                "company_notes": "",
            },
            "prospect": {
                "name": "Jordan Lee",
                "title": "VP Revenue Operations",
                "company": "Nimbus Health",
                "industry": "",
                "notes": "",
                "research_text": "Nimbus Health expanded RevOps ownership in January 2026.",
            },
            "cta": {
                "cta_type": "question",
                "cta_final_line": "Open to a quick chat to see if this is relevant?",
            },
        }
    )
    user_prompt = messages[1]["content"]
    assert "CONTAINMENT CHECK" in user_prompt
    assert "could I identify which specific input field it came from?" in user_prompt
    assert "Do not compensate for sparse input by importing training knowledge." in user_prompt
    assert "you must use ONLY these exact strings as source_field values" in user_prompt
    assert "Never use \"research\", \"research_activity\", or any other variation." in user_prompt
    assert "SEMANTIC INPUT STATE" in user_prompt
    assert "research_state=no_research means research_text contributes zero facts" in user_prompt
    assert "Placeholder/null-ish text must never appear anywhere in output" in user_prompt
    assert "sparse or no_research input should usually produce 1-3 conservative hooks." in user_prompt


def test_stage_c_single_prompt_requires_proof_gap_three_sentence_mode() -> None:
    messages = stage_c.build_single_messages(
        messaging_brief=_messaging_brief(),
        fit_map=_fit_map(),
        angle_set=_angle_set(),
        message_atoms=_atoms(proof_gap=True),
        preset={"banned_phrases_additions": []},
        sliders={"tone": 0.5, "framing": 0.5, "stance": 0.5, "length": "short"},
        cta_final_line="Open to a quick chat to see if this is relevant?",
    )
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "If message_atoms.proof_gap is true, omit proof sentence entirely." in system_prompt
    assert "write a three-sentence email: opener -> value -> CTA line" in user_prompt
    assert "Do not convert prospect facts into proof." in user_prompt


def test_stage_c_batch_prompt_mentions_proof_gap_behavior() -> None:
    messages = stage_c.build_batch_messages(
        messaging_brief=_messaging_brief(),
        fit_map=_fit_map(),
        angle_set=_angle_set(),
        message_atoms=_atoms(proof_gap=True),
        presets=[{"preset_id": "direct", "banned_phrases_additions": []}],
        sliders={"tone": 0.5, "framing": 0.5, "stance": 0.5, "length": "short"},
        cta_final_line="Open to a quick chat to see if this is relevant?",
    )
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "RULE 8 - PROOF GAP HANDLING." in system_prompt
    assert "If message_atoms.proof_gap is true, omit proof sentence across all successful variants." in system_prompt
    assert "If message_atoms.proof_gap is true, do not invent proof and do not reuse prospect facts as proof." in user_prompt
