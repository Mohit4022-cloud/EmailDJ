from __future__ import annotations

from typing import Any

import pytest

from evals import stage_judge
from app.engine.validators import build_cta_lock, opener_contract


class DummyOpenAI:
    async def chat_completion(self, **_: Any) -> dict[str, Any]:
        raise AssertionError("network call should be patched in unit tests")


def _all_pass_payload(stage: str) -> dict[str, Any]:
    criteria = stage_judge.CRITERIA_BY_STAGE[stage]
    return {
        "stage": stage,
        "scores": {criterion: 1 for criterion in criteria},
        "total": len(criteria),
        "pass": True,
        "hard_fail_triggered": False,
        "hard_fail_criteria": [],
        "failures": [],
        "warnings": [],
    }


def _proof_basis(
    *,
    kind: str,
    fact_ids: list[str] | None = None,
    source_text: str = "",
    proof_gap: bool = False,
    hook_ids: list[str] | None = None,
    fit_hypothesis_id: str = "fit_1",
) -> dict[str, Any]:
    return {
        "kind": kind,
        "source_fact_ids": list(fact_ids or []),
        "source_hook_ids": list(hook_ids or ["hook_1"]),
        "source_fit_hypothesis_id": fit_hypothesis_id,
        "grounded_span": source_text[:240],
        "source_text": source_text[:240],
        "proof_gap": proof_gap,
    }


def test_judge_user_prompt_declares_integer_total_contract() -> None:
    prompt = stage_judge._judge_user_prompt(
        stage="CONTEXT_SYNTHESIS",
        criteria=stage_judge.CRITERIA_BY_STAGE["CONTEXT_SYNTHESIS"],
        rubric_text="containment_clean",
        artifacts={"artifact": {}},
    )

    assert '"total": 6' in prompt
    assert "Use integers for scores and total." in prompt


def test_normalize_judge_payload_types_coerces_string_bools_and_ints() -> None:
    payload = stage_judge._normalize_judge_payload_types(
        {
            "stage": "CONTEXT_SYNTHESIS",
            "scores": {"containment_clean": "1", "assumptions_labeled": "0"},
            "total": "1",
            "pass": "false",
            "hard_fail_triggered": "true",
            "hard_fail_criteria": [],
            "failures": [],
            "warnings": [],
        }
    )

    assert payload["scores"]["containment_clean"] == 1
    assert payload["scores"]["assumptions_labeled"] == 0
    assert payload["total"] == 1
    assert payload["pass"] is False
    assert payload["hard_fail_triggered"] is True


def test_normalize_judge_payload_types_coerces_numeric_bools() -> None:
    payload = stage_judge._normalize_judge_payload_types(
        {
            "stage": "CONTEXT_SYNTHESIS",
            "scores": {"containment_clean": 1},
            "total": 1,
            "pass": 1,
            "hard_fail_triggered": 0,
            "hard_fail_criteria": [],
            "failures": [],
            "warnings": [],
        }
    )

    assert payload["pass"] is True
    assert payload["hard_fail_triggered"] is False


def test_stage_a_validation_source_payload_maps_eval_request_shape() -> None:
    payload = stage_judge._stage_a_validation_source_payload(
        {
            "prospect": {
                "name": "Alex Quinn",
                "title": "VP Sales",
                "company": "Plainfield Tech",
            },
            "research_text": "No verifiable external research provided.",
            "offer_lock": "Outbound QA Toolkit",
            "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
            "cta_type": "question",
            "company_context": {
                "company_name": "Signal Harbor",
                "current_product": "Outbound QA Toolkit",
                "seller_offerings": ["Sequence QA scoring"],
                "company_notes": "Supports outbound QA.",
                "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
            },
        }
    )

    assert payload["prospect"]["company"] == "Plainfield Tech"
    assert payload["prospect"]["research_text"] == "No verifiable external research provided."
    assert payload["user_company"]["product_summary"] == "Outbound QA Toolkit"
    assert payload["user_company"]["differentiators"] == ["Sequence QA scoring"]
    assert payload["cta"]["cta_final_line"] == "Open to a quick chat to see if this is relevant?"


@pytest.mark.asyncio
async def test_judge_message_atoms_hard_fail_on_bracket_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("ONE_LINER_COMPRESSOR"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "hooks": [{"hook_id": "hook_1"}],
        "hook_lineage": {"canonical_hook_ids": ["hook_1"], "hook_alias_map": {"hook_1": "hook_1"}},
        "facts_from_input": [{"source_field": "research_text", "fact_kind": "prospect_context", "text": "Company: Nimbus Health"}],
    }
    atoms = {
        "preset_id": "challenger",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "canonical_hook_ids": ["hook_1"],
        "opener_atom": "Noticed your RevOps scope expanded this quarter.",
        "opener_line": "Noticed your RevOps scope expanded this quarter.",
        "opener_contract": opener_contract(),
        "value_atom": "[Persona's team] improves process quality with our platform.",
        "proof_atom": "",
        "proof_basis": _proof_basis(kind="none", proof_gap=True),
        "cta_atom": "Open to a quick chat to see if this is relevant?",
        "cta_intent": "Ask whether a quick chat is relevant.",
        "required_cta_line": "Open to a quick chat to see if this is relevant?",
        "cta_lock": build_cta_lock("Open to a quick chat to see if this is relevant?"),
        "target_word_budget": 61,
        "target_sentence_budget": 3,
    }

    result = await stage_judge.judge_message_atoms(
        atoms,
        brief,
        {"angle_id": "angle_1"},
        locked_cta="Open to a quick chat to see if this is relevant?",
        openai=DummyOpenAI(),
    )

    assert result["hard_fail_triggered"] is True
    assert "value_outcome_not_mechanism" in result["hard_fail_criteria"]


@pytest.mark.asyncio
async def test_judge_message_atoms_hard_fail_on_circular_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("ONE_LINER_COMPRESSOR"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "hooks": [{"hook_id": "hook_1"}],
        "hook_lineage": {"canonical_hook_ids": ["hook_1"], "hook_alias_map": {"hook_1": "hook_1"}},
        "facts_from_input": [
            {
                "fact_id": "fact_1",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Nimbus Health expanded RevOps ownership in January 2026 to improve pipeline hygiene.",
            }
        ],
    }
    atoms = {
        "preset_id": "challenger",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "canonical_hook_ids": ["hook_1"],
        "opener_atom": "Noticed Nimbus Health expanded RevOps ownership.",
        "opener_line": "Noticed Nimbus Health expanded RevOps ownership.",
        "opener_contract": opener_contract(),
        "value_atom": "Teams cut handoff delays by 18% in one quarter.",
        "proof_atom": "Nimbus Health expanded RevOps ownership in January 2026 to improve pipeline hygiene.",
        "proof_basis": _proof_basis(
            kind="hard_proof",
            fact_ids=["fact_1"],
            source_text="Nimbus Health expanded RevOps ownership in January 2026 to improve pipeline hygiene.",
        ),
        "cta_atom": "Open to a quick chat to see if this is relevant?",
        "cta_intent": "Ask whether a quick chat is relevant.",
        "required_cta_line": "Open to a quick chat to see if this is relevant?",
        "cta_lock": build_cta_lock("Open to a quick chat to see if this is relevant?"),
        "target_word_budget": 61,
        "target_sentence_budget": 4,
    }

    result = await stage_judge.judge_message_atoms(
        atoms,
        brief,
        {"angle_id": "angle_1", "proof": atoms["proof_atom"]},
        locked_cta="Open to a quick chat to see if this is relevant?",
        openai=DummyOpenAI(),
    )

    assert result["hard_fail_triggered"] is True
    assert "proof_not_circular" in result["hard_fail_criteria"]


@pytest.mark.asyncio
async def test_judge_email_draft_hard_fail_on_cta_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("EMAIL_GENERATION"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    result = await stage_judge.judge_email_draft(
        {
            "subject": "RevOps quality idea",
            "body": "Hi Jordan\n\nTightening consistency can protect forecast confidence.\n\nWould you be open to a call next week?",
        },
        {
            "proof_atom": "",
            "proof_basis": _proof_basis(kind="none", proof_gap=True),
            "opener_line": "Tightening consistency can protect forecast confidence.",
            "value_atom": "Tightening consistency can protect forecast confidence.",
        },
        {},
        cta_final_line="Open to a quick chat to see if this is relevant?",
        proof_gap=True,
        openai=DummyOpenAI(),
    )

    assert result["hard_fail_triggered"] is True
    assert "cta_exact" in result["hard_fail_criteria"]


@pytest.mark.asyncio
async def test_judge_messaging_brief_passes_when_signal_strength_rules_match(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("CONTEXT_SYNTHESIS"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "research_text", "fact_kind": "prospect_context", "text": "Nimbus launched a RevOps quality program in January 2026."},
            {"fact_id": "fact_2", "source_field": "proof_points", "fact_kind": "seller_proof", "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews."},
        ],
        "assumptions": [
            {
                "assumption_id": "assump_1",
                "assumption_kind": "inferred_hypothesis",
                "text": "Nimbus may be reviewing workflow consistency during this program.",
                "confidence": 0.75,
                "confidence_label": "medium",
                "based_on_fact_ids": ["fact_1", "fact_2"],
            }
        ],
        "hooks": [
            {
                "hook_id": "h1",
                "hook_type": "initiative",
                "grounded_observation": "Nimbus launched a RevOps quality program in January 2026.",
                "inferred_relevance": "That likely means workflow consistency is under review.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Nimbus's January 2026 RevOps quality program may make consistency improvement timely.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": ["fact_2"],
                "confidence_level": "high",
                "evidence_strength": "strong",
                "risk_flags": [],
            },
            {
                "hook_id": "h2",
                "hook_type": "pain",
                "grounded_observation": "Nimbus launched a RevOps quality program in January 2026.",
                "inferred_relevance": "That may mean process drift is under scrutiny.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Quality program work may make process-drift reduction relevant.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": ["fact_2"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            },
            {
                "hook_id": "h3",
                "hook_type": "priority",
                "grounded_observation": "Nimbus launched a RevOps quality program in January 2026.",
                "inferred_relevance": "That may mean forecast consistency is a priority.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Forecast consistency may be a live priority during this program.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": ["fact_2"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            },
        ],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "prohibited_overreach": [],
        "brief_quality": {
            "fact_count": 2,
            "assumption_count": 1,
            "hook_count": 3,
            "has_research": True,
            "grounded_fact_count": 2,
            "prospect_context_fact_count": 1,
            "seller_context_fact_count": 0,
            "seller_proof_fact_count": 1,
            "cta_fact_count": 0,
            "confidence_ceiling": 0.75,
            "signal_strength": "high",
            "overreach_risk": "low",
            "quality_notes": [],
        },
    }

    result = await stage_judge.judge_messaging_brief(
        brief,
        {
            "user_company": {
                "proof_points": ["A SaaS team reduced handoff delays by 18% after sequence QA reviews."],
            },
            "prospect": {"research_text": "Nimbus launched a RevOps quality program in January 2026."},
        },
        openai=DummyOpenAI(),
    )

    assert result["pass"] is True
    assert result["scores"]["signal_strength_honest"] == 1


@pytest.mark.asyncio
async def test_judge_messaging_brief_overrides_llm_false_fail_when_validator_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return {
            "stage": "CONTEXT_SYNTHESIS",
            "scores": {
                "containment_clean": 0,
                "assumptions_labeled": 0,
                "hooks_grounded": 0,
                "confidence_calibrated": 0,
                "signal_strength_honest": 0,
                "no_prospect_as_proof": 0,
            },
            "total": 0,
            "pass": False,
            "hard_fail_triggered": True,
            "hard_fail_criteria": ["signal_strength_honest"],
            "failures": ["llm false fail"],
            "warnings": ["llm warning"],
        }, {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "company", "fact_kind": "prospect_context", "text": "Nimbus"},
            {"fact_id": "fact_2", "source_field": "research_text", "fact_kind": "prospect_context", "text": "Nimbus launched a RevOps quality program in January 2026."},
            {"fact_id": "fact_3", "source_field": "proof_points", "fact_kind": "seller_proof", "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews."},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "h1",
                "hook_type": "initiative",
                "grounded_observation": "Nimbus launched a RevOps quality program in January 2026.",
                "inferred_relevance": "That may make consistency work timely.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Nimbus's January 2026 RevOps quality program may make consistency improvement timely.",
                "supported_by_fact_ids": ["fact_2"],
                "seller_fact_ids": ["fact_3"],
                "confidence_level": "high",
                "evidence_strength": "strong",
                "risk_flags": [],
            }
        ],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "brief_quality": {"signal_strength": "high", "overreach_risk": "low"},
    }

    result = await stage_judge.judge_messaging_brief(
        brief,
        {
            "user_company": {
                "proof_points": ["A SaaS team reduced handoff delays by 18% after sequence QA reviews."],
            },
            "prospect": {"company": "Nimbus", "research_text": "Nimbus launched a RevOps quality program in January 2026."},
        },
        openai=DummyOpenAI(),
    )

    assert result["pass"] is True
    assert result["scores"]["containment_clean"] == 1
    assert result["scores"]["signal_strength_honest"] == 1
    assert "llm warning" in result["warnings"]


@pytest.mark.asyncio
async def test_judge_messaging_brief_fails_when_prospect_context_is_used_as_proof(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("CONTEXT_SYNTHESIS"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "research_text", "fact_kind": "prospect_context", "text": "Nimbus expanded RevOps ownership in January 2026."},
        ],
        "assumptions": [{"confidence": 0.6}],
        "hooks": [
            {
                "hook_id": "h1",
                "hook_type": "initiative",
                "grounded_observation": "Nimbus expanded RevOps ownership in January 2026.",
                "inferred_relevance": "That may mean consistency matters more.",
                "seller_support": "Nimbus's expansion proves our QA controls are the right fit.",
                "hook_text": "Nimbus's expansion proves our QA controls are the right fit.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": ["fact_1"],
                "confidence_level": "high",
                "evidence_strength": "strong",
                "risk_flags": [],
            }
        ],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "prohibited_overreach": ["prospect_as_proof"],
        "brief_quality": {
            "fact_count": 1,
            "assumption_count": 1,
            "hook_count": 1,
            "has_research": True,
            "grounded_fact_count": 1,
            "prospect_context_fact_count": 1,
            "seller_context_fact_count": 0,
            "seller_proof_fact_count": 0,
            "cta_fact_count": 0,
            "confidence_ceiling": 0.6,
            "signal_strength": "medium",
            "overreach_risk": "high",
            "quality_notes": [],
        },
    }

    result = await stage_judge.judge_messaging_brief(
        brief,
        {"research_text": "Nimbus expanded RevOps ownership in January 2026."},
        openai=DummyOpenAI(),
    )

    assert result["pass"] is False
    assert result["scores"]["no_prospect_as_proof"] == 0


@pytest.mark.asyncio
async def test_judge_qa_report_fails_on_non_surgical_fix_instruction(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("EMAIL_QA"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    draft = {
        "subject": "RevOps consistency",
        "body": "Nimbus expanded RevOps ownership. Teams can cut handoff delays. Open to a quick chat to see if this is relevant?",
    }
    qa = {
        "issues": [
            {
                "type": "clarity",
                "severity": "medium",
                "evidence": ["Nimbus expanded RevOps ownership."],
                "fix_instruction": "make it more specific",
            }
        ],
        "pass_rewrite_needed": True,
        "rewrite_plan": ["Tighten opener."],
    }

    result = await stage_judge.judge_qa_report(
        qa,
        draft,
        openai=DummyOpenAI(),
    )

    assert result["pass"] is False
    assert result["scores"]["fix_instructions_surgical"] == 0


@pytest.mark.asyncio
async def test_all_judges_handle_missing_artifacts() -> None:
    openai = DummyOpenAI()

    results = [
        await stage_judge.judge_messaging_brief(None, {}, openai=openai),
        await stage_judge.judge_fit_map(None, {}, openai=openai),
        await stage_judge.judge_angle_set(None, {}, {}, openai=openai),
        await stage_judge.judge_message_atoms(None, {}, {}, locked_cta="x", openai=openai),
        await stage_judge.judge_email_draft(None, {}, {}, cta_final_line="x", proof_gap=True, openai=openai),
        await stage_judge.judge_qa_report(None, {}, openai=openai),
        await stage_judge.judge_rewritten_draft(None, {}, {}, {}, cta_final_line="x", proof_gap=True, openai=openai),
    ]

    for result in results:
        assert result["pass"] is False
        assert any("artifact missing" in str(item).lower() for item in result["failures"])


@pytest.mark.asyncio
async def test_judge_angle_set_restores_grounded_why_you_why_now(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return {
            "stage": "ANGLE_PICKER",
            "scores": {
                "angles_distinct": 1,
                "hook_ids_valid": 1,
                "hypothesis_ids_valid": 1,
                "why_you_why_now_earned": 0,
                "risk_flags_inherited": 1,
                "cta_bridge_natural": 1,
            },
            "total": 5,
            "pass": True,
            "hard_fail_triggered": False,
            "hard_fail_criteria": [],
            "failures": ["llm false fail on why_you_why_now"],
            "warnings": [],
        }, {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "facts_from_input": [
            {
                "fact_id": "fact_1",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Pillar Circuit launched a February 2026 workflow audit focused on handoff latency.",
            }
        ],
        "hooks": [
            {
                "hook_id": "hook_1",
                "supported_by_fact_ids": ["fact_1"],
            },
            {
                "hook_id": "hook_2",
                "supported_by_fact_ids": ["fact_1"],
            },
            {
                "hook_id": "hook_3",
                "supported_by_fact_ids": ["fact_1"],
            },
        ],
        "hook_lineage": {
            "canonical_hook_ids": ["hook_1", "hook_2", "hook_3"],
            "hook_alias_map": {"hook_1": "hook_1", "hook_2": "hook_2", "hook_3": "hook_3"},
        },
    }
    fit_map = {
        "hypotheses": [
            {
                "fit_hypothesis_id": "hyp_1",
                "supporting_fact_ids": ["fact_1"],
                "risk_flags": [],
            }
        ]
    }
    angle_set = {
        "angles": [
            {
                "angle_id": "angle_1",
                "angle_type": "why_you_why_now",
                "rank": 1,
                "persona_fit_score": 0.91,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "hyp_1",
                "pain": "The February 2026 audit makes handoff latency newly urgent.",
                "impact": "Workflow friction stays visible during the audit window.",
                "proof": "The audit itself is the timing signal.",
                "proof_basis": _proof_basis(
                    kind="soft_signal",
                    fact_ids=["fact_1"],
                    source_text="Pillar Circuit launched a February 2026 workflow audit focused on handoff latency.",
                    hook_ids=["hook_1"],
                    fit_hypothesis_id="hyp_1",
                ),
                "primary_pain": "handoff latency",
                "primary_value_motion": "respond before the audit window closes",
                "primary_proof_basis": "soft_signal|fact_1|hook_1|workflow_audit",
                "framing_type": "why_you_why_now",
                "risk_level": "low",
                "cta_question_suggestion": "Would a short comparison be useful?",
                "risk_flags": [],
            },
            {
                "angle_id": "angle_2",
                "angle_type": "problem_led",
                "rank": 2,
                "persona_fit_score": 0.84,
                "selected_hook_id": "hook_2",
                "selected_fit_hypothesis_id": "hyp_1",
                "pain": "Manual handoff review creates workflow drag.",
                "impact": "That can keep latency hidden until later stages.",
                "proof": "Workflow QA gives managers a tighter review loop.",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="Workflow QA gives managers a tighter review loop.",
                    hook_ids=["hook_2"],
                    fit_hypothesis_id="hyp_1",
                ),
                "primary_pain": "manual handoff review",
                "primary_value_motion": "tighten review loops",
                "primary_proof_basis": "capability_statement|hook_2|review_loop",
                "framing_type": "problem_led",
                "risk_level": "medium",
                "cta_question_suggestion": "Would a short comparison be useful?",
                "risk_flags": [],
            },
            {
                "angle_id": "angle_3",
                "angle_type": "outcome_led",
                "rank": 3,
                "persona_fit_score": 0.79,
                "selected_hook_id": "hook_3",
                "selected_fit_hypothesis_id": "hyp_1",
                "pain": "Audit pressure can delay handoff fixes.",
                "impact": "That can keep review cycles slow.",
                "proof": "Workflow QA helps surface review gaps earlier.",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="Workflow QA helps surface review gaps earlier.",
                    hook_ids=["hook_3"],
                    fit_hypothesis_id="hyp_1",
                ),
                "primary_pain": "audit pressure",
                "primary_value_motion": "surface review gaps earlier",
                "primary_proof_basis": "capability_statement|hook_3|review_gaps",
                "framing_type": "outcome_led",
                "risk_level": "medium",
                "cta_question_suggestion": "Would a short comparison be useful?",
                "risk_flags": [],
            },
        ]
    }

    result = await stage_judge.judge_angle_set(angle_set, brief, fit_map, openai=DummyOpenAI())

    assert result["scores"]["why_you_why_now_earned"] == 1
    assert "deterministic_override:angle_contract_checks" in result["warnings"]


@pytest.mark.asyncio
async def test_judge_qa_report_restores_objective_structural_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return {
            "stage": "EMAIL_QA",
            "scores": {
                "evidence_quoted": 0,
                "fix_instructions_surgical": 0,
                "severity_calibrated": 0,
                "rewrite_plan_actionable": 0,
            },
            "total": 0,
            "pass": False,
            "hard_fail_triggered": False,
            "hard_fail_criteria": [],
            "failures": ["llm false fail on structured QA"],
            "warnings": [],
        }, {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    draft = {
        "subject": "Workflow QA for Pillar Circuit",
        "body": "Seeing Pillar Circuit's February 2026 workflow audit, this opener carries too many linked ideas because it stacks clauses and context. Diagnostics-driven QA helps revops leaders tighten handoff reviews.\n\nWould a quick comparison of workflow QA approaches be useful?",
    }
    qa = {
        "pass_rewrite_needed": True,
        "issues": [
            {
                "issue_code": "opener_too_complex",
                "severity": "medium",
                "offending_span_or_target_section": "opener sentence",
                "evidence_quote": "Seeing Pillar Circuit's February 2026 workflow audit, this opener carries too many linked ideas because it stacks clauses and context.",
                "fix_instruction": "Replace only the opener sentence with a simpler single-clause opener tied to the same grounded hook.",
                "expected_effect": "Make the opener easier to scan.",
            }
        ],
        "rewrite_plan": [
            {
                "issue_code": "opener_too_complex",
                "target": "opener sentence",
                "action": "Replace the opener with one simpler clause tied to the same audit signal.",
                "replacement_guidance": "Keep the audit reference but remove the stacked clause.",
            }
        ],
    }

    result = await stage_judge.judge_qa_report(qa, draft, openai=DummyOpenAI())

    assert result["scores"]["evidence_quoted"] == 1
    assert result["scores"]["fix_instructions_surgical"] == 1
    assert result["scores"]["rewrite_plan_actionable"] == 1
    assert "deterministic_override:qa_objective_checks" in result["warnings"]


@pytest.mark.asyncio
async def test_judge_rewritten_draft_restores_objective_rewrite_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return {
            "stage": "EMAIL_REWRITE",
            "scores": {
                "high_issues_resolved": 0,
                "no_new_content": 0,
                "untouched_sentences_preserved": 0,
                "cta_exact": 0,
                "metadata_preserved": 0,
            },
            "total": 0,
            "pass": False,
            "hard_fail_triggered": True,
            "hard_fail_criteria": ["cta_exact"],
            "failures": ["llm false fail on rewrite"],
            "warnings": [],
        }, {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    original = {
        "subject": "Workflow QA for Pillar Circuit",
        "body": "Pillar Circuit's audit signals handoff latency. Diagnostics-driven QA helps revops teams tighten reviews.\n\nWould a quick comparison of workflow QA approaches be useful?",
        "preset_id": "direct",
        "selected_angle_id": "angle_01",
        "used_hook_ids": ["hook_01"],
    }
    rewritten = {
        "subject": "Workflow QA for Pillar Circuit",
        "body": "Pillar Circuit's February 2026 audit signals handoff latency. Diagnostics-driven QA helps revops teams tighten reviews. That gives managers a cleaner way to act on handoff gaps before they reach forecast discussions.\n\nWould a quick comparison of workflow QA approaches be useful?",
        "preset_id": "direct",
        "selected_angle_id": "angle_01",
        "used_hook_ids": ["hook_01"],
    }
    qa = {
        "issues": [
            {
                "issue_code": "word_count_out_of_band",
                "severity": "high",
                "offending_span_or_target_section": "Pillar Circuit's audit signals handoff latency.",
                "evidence_quote": "Pillar Circuit's audit signals handoff latency.",
                "fix_instruction": "Expand only the body before the locked CTA by adding one grounded middle sentence.",
            }
        ],
        "rewrite_plan": [
            {
                "issue_code": "word_count_out_of_band",
                "target": "Pillar Circuit's audit signals handoff latency.",
                "action": "Rewrite the opener slightly and insert one grounded middle sentence after the preserved value sentence.",
                "replacement_guidance": "Keep the QA value sentence unchanged and add one concrete sentence before the CTA.",
            }
        ],
    }

    result = await stage_judge.judge_rewritten_draft(
        rewritten,
        original,
        qa,
        {
            "proof_atom": "",
            "proof_basis": _proof_basis(kind="none", proof_gap=True),
            "opener_line": "Pillar Circuit's audit signals handoff latency.",
            "value_atom": "Diagnostics-driven QA helps revops teams tighten reviews.",
        },
        cta_final_line="Would a quick comparison of workflow QA approaches be useful?",
        proof_gap=True,
        openai=DummyOpenAI(),
    )

    assert result["scores"]["cta_exact"] == 1
    assert result["scores"]["metadata_preserved"] == 1
    assert result["scores"]["high_issues_resolved"] == 1
    assert result["scores"]["no_new_content"] == 1
    assert result["scores"]["untouched_sentences_preserved"] == 1
    assert result["pass"] is True
    assert "deterministic_override:rewrite_objective_checks" in result["warnings"]


@pytest.mark.asyncio
async def test_judge_messaging_brief_warns_on_raw_hygiene_issues(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("CONTEXT_SYNTHESIS"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "company", "fact_kind": "prospect_context", "text": "Altura Stone"},
        ],
        "assumptions": [],
        "hooks": [],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "brief_quality": {"signal_strength": "low", "overreach_risk": "low"},
    }

    result = await stage_judge.judge_messaging_brief(
        brief,
        {"prospect": {"company": "Altura Stone"}},
        artifact_views={"raw_artifact_quality": {"issue_count": 3}},
        openai=DummyOpenAI(),
    )

    assert "raw_hygiene_issues_present:3" in result["warnings"]


@pytest.mark.asyncio
async def test_judge_messaging_brief_fails_on_contaminated_research(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("CONTEXT_SYNTHESIS"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "company", "fact_kind": "prospect_context", "text": "Altura Stone"},
            {"fact_id": "fact_2", "source_field": "research_text", "fact_kind": "prospect_context", "text": "Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs."},
            {"fact_id": "fact_3", "source_field": "proof_points", "fact_kind": "seller_proof", "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews."},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "h1",
                "hook_type": "initiative",
                "grounded_observation": "Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs.",
                "inferred_relevance": "That may make attribution safety relevant.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Attribution safety may be relevant while RevOps ownership is expanding.",
                "supported_by_fact_ids": ["fact_2"],
                "seller_fact_ids": ["fact_3"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            }
        ],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "brief_quality": {"signal_strength": "medium", "overreach_risk": "low"},
    }

    result = await stage_judge.judge_messaging_brief(
        brief,
        {"prospect": {"company": "Altura Stone"}},
        openai=DummyOpenAI(),
    )

    assert result["pass"] is False
    assert result["scores"]["hooks_grounded"] == 0


@pytest.mark.asyncio
async def test_judge_messaging_brief_prefers_sanitized_artifact_view_for_alignment(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("CONTEXT_SYNTHESIS"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    passing_brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "company", "fact_kind": "prospect_context", "text": "Nimbus"},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "h1",
                "hook_type": "pain",
                "grounded_observation": "Nimbus.",
                "inferred_relevance": "Role fit.",
                "seller_support": "",
                "hook_text": "Workflow QA may matter.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": [],
                "confidence_level": "low",
                "evidence_strength": "weak",
                "risk_flags": ["seller_proof_gap"],
            }
        ],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "brief_quality": {"signal_strength": "low", "overreach_risk": "low"},
    }
    failing_sanitized_brief = {
        "facts_from_input": [
            {"fact_id": "fact_1", "source_field": "company", "fact_kind": "prospect_context", "text": "Nimbus"},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "h1",
                "hook_type": "initiative",
                "grounded_observation": "Nimbus launched a program.",
                "inferred_relevance": "That makes timing urgent.",
                "seller_support": "",
                "hook_text": "This initiative is timely.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": [],
                "confidence_level": "low",
                "evidence_strength": "weak",
                "risk_flags": ["seller_proof_gap"],
            }
        ],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "brief_quality": {"signal_strength": "low", "overreach_risk": "medium"},
    }

    result = await stage_judge.judge_messaging_brief(
        passing_brief,
        {"prospect": {"company": "Nimbus"}},
        artifact_views={"sanitized_stage_a_artifact": failing_sanitized_brief},
        openai=DummyOpenAI(),
    )

    assert result["pass"] is False
    assert result["scores"]["signal_strength_honest"] == 0
