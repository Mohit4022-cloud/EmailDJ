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
                "text": "Prospect runs revenue operations.",
            }
        ],
        "assumptions": [
            {
                "assumption_id": "assumption_01",
                "text": "May prioritize workflow consistency.",
                "confidence": 0.55,
                "based_on_fact_ids": ["fact_01"],
            }
        ],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "hook_text": "RevOps teams often fight process drift.",
                "supported_by_fact_ids": ["fact_01"],
                "risk_flags": [],
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
        "forbidden_claim_patterns": ["saw your recent post"],
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
            "confidence_ceiling": 0.55,
            "signal_strength": signal_strength,
            "quality_notes": [],
        },
    }


def test_validate_messaging_brief_accepts_low_signal_for_thin_input() -> None:
    brief = _base_brief(signal_strength="low")
    validate_messaging_brief(brief, source_text="")


def test_validate_messaging_brief_rejects_incorrect_signal_strength() -> None:
    brief = _base_brief(signal_strength="medium")
    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="")

    assert "brief_quality_signal_strength_mismatch" in exc_info.value.codes
