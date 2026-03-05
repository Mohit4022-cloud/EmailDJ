from __future__ import annotations

import pytest

from app.engine.validators import ValidationIssue, validate_messaging_brief


def _base_brief() -> dict:
    return {
        "version": "1",
        "brief_id": "brief_1",
        "facts_from_input": [
            {
                "fact_id": "fact_1",
                "source_field": "research_text",
                "text": "Nimbus expanded RevOps ownership in January 2026.",
            }
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_1",
                "hook_type": "initiative",
                "hook_text": "RevOps ownership expansion indicates timing signal.",
                "supported_by_fact_ids": ["fact_1"],
                "risk_flags": [],
            }
        ],
        "persona_cues": {
            "likely_kpis": ["forecast consistency"],
            "likely_initiatives": ["handoff quality"],
            "day_to_day": ["pipeline governance"],
            "tools_stack": ["crm"],
            "notes": "",
        },
        "do_not_say": [],
        "forbidden_claim_patterns": ["saw your post", "noticed you", "congrats on"],
        "grounding_policy": {
            "no_new_facts": True,
            "no_ungrounded_personalization": True,
            "allowed_personalization_fact_sources": ["research_text"],
        },
        "brief_quality": {
            "fact_count": 1,
            "assumption_count": 0,
            "hook_count": 1,
            "has_research": True,
            "confidence_ceiling": 0.75,
            "signal_strength": "medium",
            "quality_notes": [],
        },
    }


def _source_payload() -> dict:
    return {
        "user_company": {
            "product_summary": "Outbound Workflow QA",
            "icp_description": "RevOps teams",
            "differentiators": ["Sequence QA scoring"],
            "proof_points": ["Handoff health alerts"],
            "do_not_say": [],
            "company_notes": "Helps teams tighten outbound consistency.",
        },
        "prospect": {
            "name": "Jordan Hale",
            "title": "VP Revenue Operations",
            "company": "Nimbus Forge",
            "industry": "",
            "notes": "None provided.",
            "research_text": "Nimbus expanded RevOps ownership in January 2026.",
        },
        "cta": {
            "cta_type": "question",
            "cta_final_line": "Open to a quick chat to see if this is relevant?",
        },
    }


def test_validate_messaging_brief_rejects_unknown_source_field_with_detail() -> None:
    brief = _base_brief()
    brief["facts_from_input"][0]["source_field"] = "research_activity"

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    err = exc_info.value
    assert "fact_source_field_not_allowed" in err.codes
    assert err.details
    assert err.details[0]["rejected_fact"]["source_field"] == "research_activity"


def test_validate_messaging_brief_rejects_placeholder_fact_text_with_detail() -> None:
    brief = _base_brief()
    brief["facts_from_input"][0]["source_field"] = "prospect_notes"
    brief["facts_from_input"][0]["text"] = "None provided."

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    err = exc_info.value
    assert "fact_placeholder_text" in err.codes
    assert err.details
    assert err.details[0]["rejected_fact"]["text_preview"] == "None provided."
