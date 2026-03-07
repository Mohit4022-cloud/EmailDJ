from __future__ import annotations

from dataclasses import replace

import pytest

from app.config import load_settings
from app.engine.ai_orchestrator import AIOrchestrator
from app.engine.brief_cache import BriefCache
from app.engine.validators import (
    ValidationIssue,
    build_cta_lock,
    normalize_cta_text,
    opener_contract,
    opener_is_simple,
    resolve_hook_ids,
    validate_angle_set,
    validate_fit_map,
)


def _brief() -> dict:
    return {
        "version": "1",
        "brief_id": "brief_1",
        "facts_from_input": [
            {
                "fact_id": "fact_1",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Northstar launched a workflow audit in February 2026.",
            },
            {
                "fact_id": "fact_2",
                "source_field": "proof_points",
                "fact_kind": "seller_proof",
                "text": "A fintech team reduced reply lag 18% after QA reviews.",
            },
        ],
        "hooks": [
            {
                "hook_id": "hook_1",
                "hook_type": "initiative",
                "grounded_observation": "Northstar launched a workflow audit in February 2026.",
                "inferred_relevance": "That likely puts workflow drift under review.",
                "seller_support": "A fintech team reduced reply lag 18% after QA reviews.",
                "hook_text": "Northstar's audit could make workflow QA timely.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": ["fact_2"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            }
        ],
        "hook_lineage": {
            "canonical_hook_ids": ["hook_1"],
            "hook_alias_map": {"hook_1": "hook_1", "legacy_hook_1": "hook_1"},
        },
        "persona_cues": {
            "likely_kpis": ["reply quality"],
            "likely_initiatives": ["workflow audit"],
            "day_to_day": ["review messaging quality"],
            "tools_stack": ["crm"],
            "notes": "",
        },
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {
            "no_new_facts": True,
            "no_ungrounded_personalization": True,
            "allowed_personalization_fact_sources": ["research_text", "proof_points"],
        },
        "brief_quality": {"quality_notes": []},
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


def _fit_map(*, proof_text: str, proof_basis: dict) -> dict:
    return {
        "version": "1",
        "hypotheses": [
            {
                "fit_hypothesis_id": "fit_1",
                "rank": 1,
                "selected_hook_id": "hook_1",
                "pain": "Workflow drift creates reply lag.",
                "impact": "That can slow follow-up quality.",
                "value": "QA keeps review loops tighter.",
                "proof": proof_text,
                "proof_basis": proof_basis,
                "supporting_fact_ids": ["fact_1", "fact_2"],
                "why_now": "The February 2026 audit makes drift more visible.",
                "confidence": 0.81,
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
                "persona_fit_score": 0.92,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "Workflow drift can stay hidden during audits.",
                "impact": "That can keep reply lag unresolved.",
                "value": "QA gives managers a tighter review loop.",
                "proof": "A fintech team reduced reply lag 18% after QA reviews.",
                "proof_basis": _proof_basis(
                    kind="hard_proof",
                    fact_ids=["fact_2"],
                    source_text="A fintech team reduced reply lag 18% after QA reviews.",
                ),
                "primary_pain": "workflow drift",
                "primary_value_motion": "tighten review loops",
                "primary_proof_basis": "hard_proof|fact_2|hook_1|reply_lag",
                "framing_type": "problem_led",
                "risk_level": "low",
                "cta_question_suggestion": "Would a short comparison be useful?",
                "risk_flags": [],
            },
            {
                "angle_id": "angle_2",
                "angle_type": "outcome_led",
                "rank": 2,
                "persona_fit_score": 0.86,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "Workflow drift creates reply lag.",
                "impact": "That keeps audit follow-up messy.",
                "value": "QA makes review loops faster.",
                "proof": "A fintech team reduced reply lag 18% after QA reviews.",
                "proof_basis": _proof_basis(
                    kind="hard_proof",
                    fact_ids=["fact_2"],
                    source_text="A fintech team reduced reply lag 18% after QA reviews.",
                ),
                "primary_pain": "workflow drift",
                "primary_value_motion": "tighten review loops",
                "primary_proof_basis": "hard_proof|fact_2|hook_1|reply_lag",
                "framing_type": "problem_led",
                "risk_level": "medium",
                "cta_question_suggestion": "Would a short comparison be useful?",
                "risk_flags": [],
            },
            {
                "angle_id": "angle_3",
                "angle_type": "proof_led",
                "rank": 3,
                "persona_fit_score": 0.8,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "Review drift is costly.",
                "impact": "That slows audit follow-through.",
                "value": "QA makes audit follow-through easier.",
                "proof": "Workflow QA gives managers a tighter review loop.",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="Workflow QA gives managers a tighter review loop.",
                ),
                "primary_pain": "review drift",
                "primary_value_motion": "make audit follow-through easier",
                "primary_proof_basis": "capability_statement|hook_1|review_loop",
                "framing_type": "proof_led",
                "risk_level": "medium",
                "cta_question_suggestion": "Would a short comparison be useful?",
                "risk_flags": [],
            },
        ],
    }


def test_validate_angle_set_rejects_duplicate_distinctness_signature() -> None:
    with pytest.raises(ValidationIssue) as exc:
        validate_angle_set(_angle_set(), _brief(), _fit_map(
            proof_text="A fintech team reduced reply lag 18% after QA reviews.",
            proof_basis=_proof_basis(
                kind="hard_proof",
                fact_ids=["fact_2"],
                source_text="A fintech team reduced reply lag 18% after QA reviews.",
            ),
        ))

    assert "angle_duplicate_distinctness_signature" in exc.value.codes


def test_resolve_hook_ids_repairs_alias_from_hook_lineage() -> None:
    repaired, actions = resolve_hook_ids(
        ["legacy_hook_1"],
        messaging_brief=_brief(),
        selected_hook_id="hook_1",
    )

    assert repaired == ["hook_1"]
    assert "repair_stale_hook_id_to_selected" not in actions


def test_validate_fit_map_rejects_vague_proof_on_thin_input() -> None:
    with pytest.raises(ValidationIssue) as exc:
        validate_fit_map(
            _fit_map(
                proof_text="Helps teams stay ahead.",
                proof_basis=_proof_basis(
                    kind="capability_statement",
                    source_text="Helps teams stay ahead.",
                ),
            ),
            _brief(),
        )

    assert "fit_proof_not_specific" in exc.value.codes


def test_opener_is_simple_rejects_leading_clause_stack() -> None:
    assert opener_is_simple("Northstar's audit makes workflow drift costly.", contract=opener_contract()) is True
    assert opener_is_simple(
        "Given Northstar's audit is active, workflow drift is getting more expensive.",
        contract=opener_contract(),
    ) is False


def test_reconstruct_draft_from_patch_preserves_untouched_sentence_and_cta() -> None:
    orchestrator = AIOrchestrator(
        openai=type("Disabled", (), {"enabled": lambda self: False})(),
        settings=replace(load_settings(), app_env="test"),
        brief_cache=BriefCache(),
    )
    original = {
        "version": "1",
        "preset_id": "direct",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "subject": "Workflow QA idea",
        "body": (
            "Hi Alex,\n\n"
            "Northstar's audit puts workflow drift under review. "
            "QA gives managers a tighter review loop.\n\n"
            "Open to a quick chat to see if this is relevant?"
        ),
    }
    patch = {
        "version": "1",
        "preset_id": "direct",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "cta_lock": build_cta_lock("Open to a quick chat to see if this is relevant?"),
        "preserve_sentence_indexes": [1],
        "sentence_operations": [
            {
                "issue_code": "opener_too_complex",
                "action": "rewrite",
                "target_sentence_index": 0,
                "text": "Hi Alex, Northstar's audit makes workflow drift harder to ignore.",
            }
        ],
    }

    rebuilt, details = orchestrator._reconstruct_draft_from_patch(  # noqa: SLF001
        patch=patch,
        original_draft=original,
        cta_line="Open to a quick chat to see if this is relevant?",
    )

    assert "QA gives managers a tighter review loop." in rebuilt["body"]
    assert rebuilt["body"].rstrip().endswith("Open to a quick chat to see if this is relevant?")
    assert details["rewrite_patch_dropped_operations"] == []


def test_cta_lock_normalization_is_shared() -> None:
    assert normalize_cta_text(" Open to  a quick chat to see if this is relevant? ") == "Open to a quick chat to see if this is relevant?"
