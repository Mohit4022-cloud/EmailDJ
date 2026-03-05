from __future__ import annotations

from typing import Any

import pytest

from evals import stage_judge


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


@pytest.mark.asyncio
async def test_judge_message_atoms_hard_fail_on_bracket_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_call_judge_llm(*, openai, messages, timeout_seconds=45.0):  # noqa: ARG001
        return _all_pass_payload("ONE_LINER_COMPRESSOR"), {"usage": {}}

    monkeypatch.setattr(stage_judge, "_call_judge_llm", _fake_call_judge_llm)

    brief = {
        "hooks": [{"hook_id": "hook_1"}],
        "facts_from_input": [{"source_field": "prospect_context", "text": "Company: Nimbus Health"}],
    }
    atoms = {
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "opener_line": "Noticed your RevOps scope expanded this quarter.",
        "value_line": "[Persona's team] improves process quality with our platform.",
        "proof_line": "",
        "cta_line": "Open to a quick chat to see if this is relevant?",
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
        "facts_from_input": [
            {
                "source_field": "research_text",
                "text": "Nimbus Health expanded RevOps ownership in January 2026 to improve pipeline hygiene.",
            }
        ],
    }
    atoms = {
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "opener_line": "Noticed Nimbus Health expanded RevOps ownership.",
        "value_line": "Teams cut handoff delays by 18% in one quarter.",
        "proof_line": "Nimbus Health expanded RevOps ownership in January 2026 to improve pipeline hygiene.",
        "cta_line": "Open to a quick chat to see if this is relevant?",
    }

    result = await stage_judge.judge_message_atoms(
        atoms,
        brief,
        {"angle_id": "angle_1", "proof": atoms["proof_line"]},
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
        {"proof_line": ""},
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
        "facts_from_input": [{"fact_id": f"fact_{idx}", "source_field": "research_text", "text": f"fact {idx}"} for idx in range(1, 7)],
        "assumptions": [{"confidence": 0.75}],
        "hooks": [{"hook_id": "h1"}, {"hook_id": "h2"}, {"hook_id": "h3"}],
        "forbidden_claim_patterns": ["saw your post", "noticed you", "congrats on"],
        "brief_quality": {
            "fact_count": 6,
            "hook_count": 3,
            "has_research": True,
            "signal_strength": "high",
        },
    }

    result = await stage_judge.judge_messaging_brief(
        brief,
        {"research_text": "facts"},
        openai=DummyOpenAI(),
    )

    assert result["pass"] is True
    assert result["scores"]["signal_strength_honest"] == 1


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
