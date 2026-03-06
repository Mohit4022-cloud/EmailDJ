from __future__ import annotations

import pytest

from app.engine.validators import ValidationIssue, validate_messaging_brief


def _base_brief(*, signal_strength: str) -> dict:
    return {
        "version": "1",
        "brief_id": "brief_low_signal",
        "facts_from_input": [
            {
                "fact_id": "fact_01",
                "source_field": "prospect_notes",
                "fact_kind": "prospect_context",
                "text": "Prospect runs revenue operations.",
            }
        ],
        "assumptions": [
            {
                "assumption_id": "assumption_01",
                "assumption_kind": "inferred_hypothesis",
                "text": "May prioritize workflow consistency.",
                "confidence": 0.55,
                "confidence_label": "medium",
                "based_on_fact_ids": ["fact_01"],
            }
        ],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "grounded_observation": "Prospect runs revenue operations.",
                "inferred_relevance": "That may mean workflow consistency matters.",
                "seller_support": "",
                "hook_text": "RevOps teams often fight process drift.",
                "supported_by_fact_ids": ["fact_01"],
                "seller_fact_ids": [],
                "confidence_level": "low",
                "evidence_strength": "weak",
                "risk_flags": ["seller_proof_gap"],
            }
        ],
        "persona_cues": {
            "likely_kpis": ["pipeline quality"],
            "likely_initiatives": ["process consistency"],
            "day_to_day": ["manage workflow"],
            "tools_stack": ["crm"],
            "notes": "",
        },
        "do_not_say": [],
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "prohibited_overreach": [],
        "grounding_policy": {
            "no_new_facts": True,
            "no_ungrounded_personalization": True,
            "allowed_personalization_fact_sources": [],
        },
        "brief_quality": {
            "fact_count": 1,
            "assumption_count": 1,
            "hook_count": 1,
            "has_research": False,
            "grounded_fact_count": 1,
            "prospect_context_fact_count": 1,
            "seller_context_fact_count": 0,
            "seller_proof_fact_count": 0,
            "cta_fact_count": 0,
            "confidence_ceiling": 0.55,
            "signal_strength": signal_strength,
            "overreach_risk": "low",
            "quality_notes": [],
        },
    }


def _source_payload() -> dict:
    return {
        "user_company": {
            "product_summary": "Workflow QA Platform",
            "icp_description": "RevOps teams reduce process drift in outbound execution.",
            "differentiators": ["Messaging consistency analytics"],
            "proof_points": ["A SaaS team reduced handoff delays by 18% after sequence QA reviews."],
            "do_not_say": [],
            "company_notes": "Supports GTM teams with repeatable messaging workflows.",
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


def test_validate_messaging_brief_accepts_low_signal_for_thin_input() -> None:
    brief = _base_brief(signal_strength="low")
    validate_messaging_brief(brief, source_text="", source_payload=_source_payload())
    assert brief["brief_quality"]["signal_strength"] == "low"


def test_validate_messaging_brief_accepts_medium_signal_with_seller_proof_but_no_research() -> None:
    brief = _base_brief(signal_strength="medium")
    brief["facts_from_input"].append(
        {
            "fact_id": "fact_02",
            "source_field": "proof_points",
            "fact_kind": "seller_proof",
            "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
        }
    )
    brief["hooks"][0]["seller_support"] = "A SaaS team reduced handoff delays by 18% after sequence QA reviews."
    brief["hooks"][0]["seller_fact_ids"] = ["fact_02"]
    brief["hooks"][0]["confidence_level"] = "medium"
    brief["hooks"][0]["evidence_strength"] = "moderate"
    brief["hooks"][0]["risk_flags"] = []
    brief["brief_quality"].update(
        {
            "fact_count": 2,
            "grounded_fact_count": 2,
            "seller_proof_fact_count": 1,
            "signal_strength": "medium",
        }
    )

    validate_messaging_brief(brief, source_text="", source_payload=_source_payload())
    assert brief["brief_quality"]["signal_strength"] == "medium"


def test_validate_messaging_brief_accepts_high_signal_when_research_and_seller_proof_are_both_grounded() -> None:
    brief = _base_brief(signal_strength="high")
    brief["facts_from_input"] = [
        {
            "fact_id": "fact_01",
            "source_field": "research_text",
            "fact_kind": "prospect_context",
            "text": "Nimbus Health expanded RevOps ownership in January 2026.",
        },
        {
            "fact_id": "fact_02",
            "source_field": "proof_points",
            "fact_kind": "seller_proof",
            "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
        },
    ]
    brief["assumptions"][0]["based_on_fact_ids"] = ["fact_01", "fact_02"]
    brief["hooks"][0].update(
        {
            "grounded_observation": "Nimbus Health expanded RevOps ownership in January 2026.",
            "inferred_relevance": "That likely means workflow consistency is being inspected closely.",
            "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
            "hook_text": "Nimbus Health's January 2026 RevOps expansion may make workflow consistency improvement timely.",
            "supported_by_fact_ids": ["fact_01"],
            "seller_fact_ids": ["fact_02"],
            "confidence_level": "high",
            "evidence_strength": "strong",
            "risk_flags": [],
        }
    )
    brief["brief_quality"].update(
        {
            "fact_count": 2,
            "grounded_fact_count": 2,
            "prospect_context_fact_count": 1,
            "seller_proof_fact_count": 1,
            "has_research": True,
            "signal_strength": "high",
            "overreach_risk": "low",
        }
    )

    validate_messaging_brief(
        brief,
        source_text="Nimbus Health expanded RevOps ownership in January 2026.",
        source_payload=_source_payload(),
    )
    assert brief["brief_quality"]["signal_strength"] == "high"


def test_validate_messaging_brief_derives_signal_strength_and_counts() -> None:
    brief = _base_brief(signal_strength="medium")
    brief["brief_quality"].update(
        {
            "fact_count": 9,
            "grounded_fact_count": 9,
            "signal_strength": "high",
        }
    )

    validate_messaging_brief(brief, source_text="", source_payload=_source_payload())

    assert brief["brief_quality"]["fact_count"] == 1
    assert brief["brief_quality"]["grounded_fact_count"] == 1
    assert brief["brief_quality"]["signal_strength"] == "low"


def test_validate_messaging_brief_rejects_unknown_fact_source_field() -> None:
    brief = _base_brief(signal_strength="low")
    brief["facts_from_input"][0]["source_field"] = "customer_feedback"
    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="", source_payload=_source_payload())

    assert "fact_source_field_not_allowed" in exc_info.value.codes


def test_validate_messaging_brief_rejects_fact_not_grounded_in_input() -> None:
    brief = _base_brief(signal_strength="low")
    brief["facts_from_input"][0]["text"] = "Customers report difficulty tracking order status."
    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="", source_payload=_source_payload())

    assert "fact_not_grounded_in_input" in exc_info.value.codes


def test_validate_messaging_brief_derives_has_research_from_source_text() -> None:
    brief = _base_brief(signal_strength="low")
    brief["brief_quality"]["has_research"] = False
    validate_messaging_brief(
        brief,
        source_text="Nimbus Health expanded RevOps ownership in January 2026.",
        source_payload=_source_payload(),
    )

    assert brief["brief_quality"]["has_research"] is True


def test_validate_messaging_brief_accepts_placeholder_research_as_no_research() -> None:
    brief = _base_brief(signal_strength="low")
    brief["brief_quality"]["has_research"] = False
    validate_messaging_brief(
        brief,
        source_text="No verifiable external research provided.",
        source_payload=_source_payload(),
    )
    assert brief["brief_quality"]["has_research"] is False


@pytest.mark.parametrize(
    "placeholder_text",
    [
        "Limited public context.",
        "No specific research available for this account.",
        "Unknown",
        "No research.",
        "No verifiable research available.",
    ],
)
def test_validate_messaging_brief_treats_research_placeholders_as_thin_input(placeholder_text: str) -> None:
    brief = _base_brief(signal_strength="low")
    brief["brief_quality"]["has_research"] = False
    validate_messaging_brief(
        brief,
        source_text=placeholder_text,
        source_payload=_source_payload(),
    )
    assert brief["brief_quality"]["has_research"] is False
