from __future__ import annotations

from app.engine.prompts import stage_a, stage_b, stage_c, stage_c0, stage_d, stage_e
from app.engine.validators import PROOF_GAP_TEXT, build_cta_lock, opener_contract


def _messaging_brief() -> dict:
    return {
        "version": "1",
        "brief_id": "brief_1",
        "facts_from_input": [
            {
                "fact_id": "fact_1",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Nimbus expanded RevOps ownership in January 2026.",
            },
            {
                "fact_id": "fact_2",
                "source_field": "proof_points",
                "fact_kind": "seller_proof",
                "text": "A fintech team lifted meetings after sequence QA.",
            },
        ],
        "hooks": [{"hook_id": "hook_1", "supported_by_fact_ids": ["fact_1"], "seller_fact_ids": ["fact_2"]}],
        "hook_lineage": {
            "canonical_hook_ids": ["hook_1"],
            "hook_alias_map": {"hook_1": "hook_1"},
        },
    }


def _proof_basis(*, kind: str, fact_ids: list[str] | None = None, source_text: str = "", proof_gap: bool = False) -> dict:
    return {
        "kind": kind,
        "source_fact_ids": list(fact_ids or []),
        "source_hook_ids": ["hook_1"],
        "source_fit_hypothesis_id": "fit_1",
        "grounded_span": source_text[:240],
        "source_text": source_text[:240],
        "proof_gap": proof_gap,
    }


def _fit_map() -> dict:
    return {
        "version": "1",
        "hypotheses": [
            {
                "fit_hypothesis_id": "fit_1",
                "rank": 1,
                "selected_hook_id": "hook_1",
                "pain": "Sequence drift can creep in during RevOps expansion.",
                "impact": "That can make pipeline quality less consistent.",
                "value": "Tighter QA keeps messaging execution more consistent.",
                "proof": "A fintech team lifted meetings after sequence QA.",
                "proof_basis": _proof_basis(
                    kind="soft_signal",
                    fact_ids=["fact_2"],
                    source_text="A fintech team lifted meetings after sequence QA.",
                ),
                "supporting_fact_ids": ["fact_1", "fact_2"],
                "why_now": "The January 2026 RevOps expansion makes execution drift more visible.",
                "confidence": 0.82,
                "risk_flags": [],
            }
        ],
    }


def _angle_set() -> dict:
    return {
        "version": "1",
        "angles": [
            {
                "angle_id": "angle_1",
                "angle_type": "problem_led",
                "rank": 1,
                "persona_fit_score": 0.86,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "RevOps expansion can expose workflow drift.",
                "impact": "That can show up as inconsistent reply quality.",
                "value": "Protect forecast consistency",
                "proof": "A SaaS team improved reply quality after tightening QA.",
                "proof_basis": _proof_basis(
                    kind="soft_signal",
                    fact_ids=["fact_2"],
                    source_text="A fintech team lifted meetings after sequence QA.",
                ),
                "primary_pain": "workflow drift",
                "primary_value_motion": "protect forecast consistency",
                "primary_proof_basis": "soft_signal|fact_2|hook_1|a fintech team lifted meetings after sequence qa",
                "framing_type": "problem_led",
                "risk_level": "low",
                "cta_question_suggestion": "Open to a quick chat to see if this is relevant?",
                "risk_flags": [],
            }
        ],
    }


def _atoms(*, proof_gap: bool) -> dict:
    proof_atom = "" if proof_gap else "A fintech team lifted meetings after sequence QA."
    proof_basis = (
        _proof_basis(kind="none", source_text="", proof_gap=True)
        if proof_gap
        else _proof_basis(
            kind="soft_signal",
            fact_ids=["fact_2"],
            source_text="A fintech team lifted meetings after sequence QA.",
        )
    )
    return {
        "version": "1",
        "preset_id": "challenger",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "canonical_hook_ids": ["hook_1"],
        "opener_atom": "Nimbus expanded RevOps ownership in January 2026.",
        "opener_line": "Nimbus expanded RevOps ownership in January 2026.",
        "opener_contract": opener_contract(),
        "value_atom": "RevOps teams cut forecasting variance in one quarter.",
        "proof_atom": proof_atom,
        "proof_basis": proof_basis,
        "cta_atom": "Open to a quick chat to see if this is relevant?",
        "cta_intent": "Ask whether a quick chat is relevant.",
        "required_cta_line": "Open to a quick chat to see if this is relevant?",
        "cta_lock": build_cta_lock("Open to a quick chat to see if this is relevant?"),
        "target_word_budget": 61,
        "target_sentence_budget": 3 if proof_gap else 4,
    }


def _budget_plan(*, proof_gap: bool) -> dict:
    return {
        "preset_id": "challenger",
        "length": "short",
        "target_total_words": 61,
        "allowed_min_words": 46,
        "allowed_max_words": 88,
        "target_sentence_count": 3 if proof_gap else 4,
        "target_sentence_floor": 3 if proof_gap else 4,
        "allowed_max_sentences": 5,
        "per_atom_word_guidance": {
            "opener_atom": 14,
            "value_atom": 20,
            "proof_atom": 10 if not proof_gap else 0,
            "cta_atom": 11,
        },
        "atom_structure": ["opener", "value", "cta"] if proof_gap else ["opener", "value", "proof", "cta"],
        "atom_total_words": 0,
        "atom_total_sentences": 0,
        "feasibility_status": "feasible",
        "feasibility_reason": "atoms_fit_current_contract",
    }


def _preset_contract() -> dict:
    return {
        "length": "short",
        "tone": "insight-led and pragmatic",
        "assertiveness": "high",
        "opener_directness": "direct",
        "cta_placement": "final_exact",
        "proof_density": "tight",
        "target_word_range": {"min": 52, "max": 78},
        "hard_word_range": {"min": 46, "max": 88},
        "sentence_count_guidance": {"target_min": 3, "target_max": 4, "hard_max": 5},
    }


def test_stage_c0_prompt_contains_value_formula_and_external_proof_rule() -> None:
    messages = stage_c0.build_messages(
        messaging_brief=_messaging_brief(),
        fit_map=_fit_map(),
        angle_set=_angle_set(),
        selected_angle_id="angle_1",
        preset_id="challenger",
        preset_contract=_preset_contract(),
        budget_plan=_budget_plan(proof_gap=False),
        sliders={"tone": 0.5, "framing": 0.5, "stance": 0.5, "length": "short"},
        cta_final_line="Open to a quick chat to see if this is relevant?",
    )
    user_prompt = messages[1]["content"]

    assert "value_atom formula (use this structure exactly)" in user_prompt
    assert "[Persona's team] [specific verb: cut/reduced/protected/freed]" in user_prompt
    assert "If no brief proof point supports this formula, set proof_atom to empty string \"\"." in user_prompt
    assert "never use the prospect's own facts as proof" in user_prompt
    assert "If seller_proof_fact_count is 0 or selected_angle risk flags include proof_gap / seller_proof_gap, proof_atom must be empty string." in messages[0]["content"]
    assert "used_hook_ids: non-empty, deduped" in user_prompt
    assert "target_word_budget: copy budget_plan.target_total_words exactly." in user_prompt


def test_stage_b_prompt_requires_exact_proof_gap_phrase_and_no_invented_numbers() -> None:
    messages = stage_b.build_messages(_messaging_brief())
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "Proof gap: no seller proof provided in brief." in system_prompt
    assert "RULE 4 - NO INVENTED NUMBERS." in system_prompt
    assert "supporting_fact_ids: list only the exact fact ids you actually used" in user_prompt
    assert 'proof is either grounded in seller-side evidence or exactly "Proof gap: no seller proof provided in brief."' in user_prompt


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
    assert "the system will canonicalize evidence origin from source_field" in user_prompt.lower()
    assert "Prospect/company context must never appear as seller proof." in user_prompt
    assert "Every hook must separate four layers" in user_prompt
    assert "Do not imply specific initiatives without evidence." in user_prompt
    assert "Do not imply recent events without evidence." in user_prompt
    assert "high confidence or strong evidence_strength require at least one seller_proof fact" in user_prompt
    assert "grounding_policy defaults and final brief_quality rollups are system-derived" in user_prompt
    assert "Sparse no-research negative example:" in user_prompt
    assert "Contamination negative example:" in user_prompt
    assert "Omission-not-placeholder example:" in user_prompt
    assert "True seller-proof positive example:" in user_prompt


def test_stage_c_single_prompt_requires_proof_gap_budget_aware_sentence_mode() -> None:
    messages = stage_c.build_single_messages(
        messaging_brief=_messaging_brief(),
        fit_map=_fit_map(),
        angle_set=_angle_set(),
        message_atoms=_atoms(proof_gap=True),
        preset={"banned_phrases_additions": [], "output_contract": {"lengths": {}}},
        preset_contract=_preset_contract(),
        budget_plan=_budget_plan(proof_gap=True),
        sliders={"tone": 0.5, "framing": 0.5, "stance": 0.5, "length": "short"},
        cta_final_line="Open to a quick chat to see if this is relevant?",
    )
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "If message_atoms.proof_atom is empty, omit proof sentence entirely." in system_prompt
    assert "RULE 5 - PRESET CONTRACT IS ACTIVE." in system_prompt
    assert "Use a three-sentence email only when that still satisfies budget_plan.allowed_min_words." in user_prompt
    assert "add one grounded impact sentence before the CTA" in user_prompt
    assert "Keep body within budget_plan allowed_min_words/allowed_max_words" in user_prompt
    assert "Do not convert prospect facts into proof." in user_prompt


def test_stage_c_batch_prompt_mentions_proof_gap_behavior() -> None:
    messages = stage_c.build_batch_messages(
        messaging_brief=_messaging_brief(),
        fit_map=_fit_map(),
        angle_set=_angle_set(),
        message_atoms=_atoms(proof_gap=True),
        presets=[{"preset_id": "direct", "banned_phrases_additions": [], "output_contract": {"lengths": {}}}],
        budget_plan_by_preset={"direct": _budget_plan(proof_gap=True)},
        sliders={"tone": 0.5, "framing": 0.5, "stance": 0.5, "length": "short"},
        cta_final_line="Open to a quick chat to see if this is relevant?",
    )
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "RULE 6 - PRESET CONTRACTS ARE ACTIVE." in system_prompt
    assert "RULE 7 - BUDGET PLANS ARE ACTIVE." in system_prompt
    assert "RULE 10 - PROOF GAP HANDLING." in system_prompt
    assert "If message_atoms.proof_atom is empty, omit proof sentence across all successful variants." in system_prompt
    assert "If message_atoms.proof_atom is empty, do not invent proof and do not reuse prospect facts as proof." in user_prompt


def test_stage_d_prompt_requires_preset_specific_issue_types() -> None:
    messages = stage_d.build_messages(
        email_draft={"subject": "x", "body": "Hi Alex.\n\nOpen to a quick chat to see if this is relevant?"},
        messaging_brief=_messaging_brief(),
        message_atoms=_atoms(proof_gap=False),
        cta_final_line="Open to a quick chat to see if this is relevant?",
        preset_contract=_preset_contract(),
        budget_plan=_budget_plan(proof_gap=False),
    )
    system_prompt = messages[0]["content"]
    user_prompt = messages[1]["content"]

    assert "RULE 8 - PRESET CONTRACT IS ACTIVE." in system_prompt
    assert "RULE 9 - BUDGET PLAN IS ACTIVE." in system_prompt
    assert "word_count_out_of_band, opener_too_soft_for_preset" in user_prompt
    assert "issue_code, type, severity, offending_span_or_target_section, evidence_quote, evidence" in user_prompt
    assert "\"budget_plan\"" in user_prompt
    assert "\"preset_contract\"" in user_prompt


def test_stage_e_rewrite_and_salvage_prompts_target_preset_contract() -> None:
    rewrite_messages = stage_e.build_messages(
        email_draft={"subject": "x", "body": "Hi Alex.\n\nOpen to a quick chat to see if this is relevant?"},
        qa_report={
            "version": "1.0",
            "pass_rewrite_needed": True,
            "issues": [
                {
                    "issue_code": "word_count_out_of_band",
                    "severity": "high",
                    "offending_span_or_target_section": "Hi Alex.",
                    "evidence_quote": "Hi Alex.",
                    "why_it_fails": "The body is too short for the preset contract.",
                    "fix_instruction": "Expand the body slightly while keeping the locked CTA exact.",
                    "expected_effect": "Bring the draft back inside the preset band.",
                }
            ],
            "risk_flags": [],
            "rewrite_plan": [
                {
                    "issue_code": "word_count_out_of_band",
                    "target": "Hi Alex.",
                    "action": "Expand the body slightly with grounded copy before the CTA.",
                    "replacement_guidance": "Use only grounded wording already supported by the brief and atoms.",
                    "preserve": 'Keep the locked CTA text "Open to a quick chat to see if this is relevant?" unchanged and leave unrelated grounded sentences untouched.',
                    "expected_effect": "Bring the draft back inside the preset band.",
                }
            ],
        },
        messaging_brief=_messaging_brief(),
        message_atoms=_atoms(proof_gap=False),
        cta_final_line="Open to a quick chat to see if this is relevant?",
        preset_contract=_preset_contract(),
        budget_plan=_budget_plan(proof_gap=False),
        sliders={"tone": 0.5, "length": "short"},
    )
    salvage_messages = stage_e.build_salvage_messages(
        email_draft={"subject": "x", "body": "Hi Alex.\n\nOpen to a quick chat to see if this is relevant?"},
        message_atoms=_atoms(proof_gap=False),
        messaging_brief=_messaging_brief(),
        cta_final_line="Open to a quick chat to see if this is relevant?",
        preset_contract=_preset_contract(),
        budget_plan=_budget_plan(proof_gap=False),
        failure_code="word_count_out_of_band",
    )

    rewrite_system = rewrite_messages[0]["content"]
    rewrite_user = rewrite_messages[1]["content"]
    salvage_system = salvage_messages[0]["content"]
    salvage_user = salvage_messages[1]["content"]

    assert "RULE 7 - PRESET CONTRACT IS ACTIVE." in rewrite_system
    assert "RULE 4 - CTA LOCK." in rewrite_system
    assert "Return EmailRewritePatch JSON with preserve_sentence_indexes and sentence_operations." in rewrite_system
    assert "Map each rewrite_plan action object to the exact sentence indexes in rewrite_context before editing." in rewrite_user
    assert "Validate the patch against schema, atoms grounding, preserve list discipline, CTA lock, preset contract, and budget plan." in rewrite_user
    assert "This is not a fresh rewrite." in salvage_system
    assert "RULE 6 - BUDGET PLAN IS ACTIVE." in salvage_system
    assert "Do not replace the draft with a new template or canned preset body." in salvage_user
