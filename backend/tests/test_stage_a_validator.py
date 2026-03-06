from __future__ import annotations

import pytest

from app.engine.normalize import normalize_generate_request
from app.schemas import ContactProfile, TargetAccountProfile, WebCompanyContext, WebGenerateRequest, WebProspectInput, WebStyleProfile
from app.engine.validators import ValidationIssue, validate_messaging_brief


def _base_brief() -> dict:
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
                "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
            },
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_1",
                "hook_type": "initiative",
                "grounded_observation": "Nimbus expanded RevOps ownership in January 2026.",
                "inferred_relevance": "That may signal active workflow scrutiny.",
                "seller_support": "",
                "hook_text": "RevOps ownership expansion may make workflow consistency conversations timely.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": [],
                "confidence_level": "medium",
                "evidence_strength": "weak",
                "risk_flags": ["seller_proof_gap"],
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
        "forbidden_claim_patterns": ["saw your recent post", "noticed you recently", "congrats on [anything not in research_text]"],
        "prohibited_overreach": [],
        "grounding_policy": {
            "no_new_facts": True,
            "no_ungrounded_personalization": True,
            "allowed_personalization_fact_sources": ["research_text"],
        },
        "brief_quality": {
            "fact_count": 2,
            "assumption_count": 0,
            "hook_count": 1,
            "has_research": True,
            "grounded_fact_count": 2,
            "prospect_context_fact_count": 1,
            "seller_context_fact_count": 0,
            "seller_proof_fact_count": 1,
            "cta_fact_count": 0,
            "confidence_ceiling": 0.75,
            "signal_strength": "medium",
            "overreach_risk": "low",
            "quality_notes": [],
        },
    }


def _source_payload() -> dict:
    return {
        "user_company": {
            "product_summary": "Outbound Workflow QA",
            "icp_description": "RevOps teams",
            "differentiators": ["Sequence QA scoring"],
            "proof_points": ["A SaaS team reduced handoff delays by 18% after sequence QA reviews."],
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
    assert err.details[0]["source_field"] == "research_activity"


def test_validate_messaging_brief_rejects_placeholder_fact_text_with_detail() -> None:
    brief = _base_brief()
    brief["facts_from_input"][0]["source_field"] = "prospect_notes"
    brief["facts_from_input"][0]["fact_kind"] = "prospect_context"
    brief["facts_from_input"][0]["text"] = "None provided."

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    err = exc_info.value
    assert "fact_placeholder_text" in err.codes
    assert err.details
    assert err.details[0]["offending_text"] == "None provided."


def test_validate_messaging_brief_rejects_placeholder_persona_cues() -> None:
    brief = _base_brief()
    brief["persona_cues"]["tools_stack"] = ["unknown"]

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    assert "persona_placeholder_text" in exc_info.value.codes


def test_validate_messaging_brief_derives_allowed_personalization_sources_from_usable_input() -> None:
    brief = _base_brief()
    brief["grounding_policy"]["allowed_personalization_fact_sources"] = ["prospect_notes"]

    validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    allowed = brief["grounding_policy"]["allowed_personalization_fact_sources"]
    assert "prospect_notes" not in allowed
    assert "research_text" in allowed
    assert "proof_points" in allowed


def test_validate_messaging_brief_rejects_prospect_as_proof_leakage() -> None:
    brief = _base_brief()
    brief["hooks"][0]["seller_support"] = "Nimbus's expansion proves our workflow QA is relevant."
    brief["hooks"][0]["seller_fact_ids"] = ["fact_1"]
    brief["prohibited_overreach"] = ["prospect_as_proof"]
    brief["brief_quality"]["overreach_risk"] = "high"
    brief["brief_quality"]["signal_strength"] = "medium"

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    assert "hook_seller_fact_id_not_seller_side" in exc_info.value.codes or "hook_prospect_as_proof" in exc_info.value.codes


def test_validate_messaging_brief_rejects_unsupported_initiative_hook() -> None:
    brief = _base_brief()
    brief["facts_from_input"][0]["source_field"] = "title"
    brief["facts_from_input"][0]["fact_kind"] = "prospect_context"
    brief["facts_from_input"][0]["text"] = "VP Revenue Operations"
    brief["hooks"][0]["grounded_observation"] = "As VP Revenue Operations, you are likely running a quality initiative."
    brief["hooks"][0]["supported_by_fact_ids"] = ["fact_1"]
    brief["hooks"][0]["hook_text"] = "Your quality initiative may make this timely."

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="", source_payload=_source_payload())

    assert "hook_unsupported_recency_or_initiative" in exc_info.value.codes


def test_validate_messaging_brief_derives_fact_kind_from_source_field() -> None:
    brief = _base_brief()
    brief["facts_from_input"][1]["fact_kind"] = "seller_context"

    validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    assert brief["facts_from_input"][1]["fact_kind"] == "seller_proof"


def test_normalize_generate_request_classifies_placeholder_research_as_no_research() -> None:
    req = WebGenerateRequest(
        prospect=WebProspectInput(
            name="Jordan Hale",
            title="VP Revenue Operations",
            company="Nimbus Forge",
            company_url="https://nimbus.example",
            linkedin_url="https://linkedin.com/in/jordan",
        ),
        prospect_first_name="Jordan",
        research_text="No verifiable external research provided.",
        offer_lock="Outbound Workflow QA",
        cta_offer_lock="Open to a quick chat to see if this is relevant?",
        response_contract="email_json_v1",
        style_profile=WebStyleProfile(),
        company_context=WebCompanyContext(
            company_name="Signal Harbor",
            current_product="Outbound Workflow QA",
            seller_offerings=["Sequence QA scoring"],
            company_notes="Helps teams tighten outbound consistency.",
            cta_offer_lock="Open to a quick chat to see if this is relevant?",
            cta_type="question",
        ),
    )

    ctx = normalize_generate_request(req)

    assert ctx.research_state == "no_research"
    assert ctx.usable_research_text == ""
    assert ctx.signal_available is False


def test_normalize_generate_request_keeps_prospect_context_out_of_seller_proof() -> None:
    req = WebGenerateRequest(
        prospect=WebProspectInput(
            name="Jordan Hale",
            title="VP Revenue Operations",
            company="Nimbus Forge",
            company_url="https://nimbus.example",
            linkedin_url="https://linkedin.com/in/jordan",
        ),
        prospect_first_name="Jordan",
        research_text="No verifiable external research provided.",
        offer_lock="Outbound Workflow QA",
        cta_offer_lock="Open to a quick chat to see if this is relevant?",
        response_contract="email_json_v1",
        style_profile=WebStyleProfile(),
        company_context=WebCompanyContext(
            company_name="Signal Harbor",
            current_product="Outbound Workflow QA",
            seller_offerings=["Sequence QA scoring"],
            company_notes="Helps teams tighten outbound consistency.",
            cta_offer_lock="Open to a quick chat to see if this is relevant?",
            cta_type="question",
        ),
        sender_profile_override=None,
        target_profile_override=None,
    )

    ctx = normalize_generate_request(
        req.model_copy(
            update={
                "target_profile_override": TargetAccountProfile(
                    official_domain="nimbus.example",
                    summary="RevOps team is tightening handoffs.",
                    proof_points=["Nimbus cut delays after ownership changes."],
                ),
                "contact_profile_override": ContactProfile(
                    name="Jordan Hale",
                    current_title="VP Revenue Operations",
                    company="Nimbus Forge",
                    role_summary="Owns RevOps systems.",
                    talking_points=["Working on forecast consistency."],
                ),
            }
        )
    )

    assert "Nimbus cut delays after ownership changes." not in ctx.seller_proof_points
    assert "Working on forecast consistency." not in ctx.seller_proof_points


def test_validate_messaging_brief_requires_seller_proof_gap_for_empty_support() -> None:
    brief = _base_brief()
    brief["hooks"][0]["risk_flags"] = []

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    assert "hook_missing_seller_proof_gap" in exc_info.value.codes


def test_validate_messaging_brief_rejects_high_confidence_seller_context_only_hook() -> None:
    brief = _base_brief()
    brief["facts_from_input"].append(
        {
            "fact_id": "fact_3",
            "source_field": "product_summary",
            "fact_kind": "seller_context",
            "text": "Outbound Workflow QA",
        }
    )
    brief["hooks"][0]["seller_support"] = "Outbound Workflow QA can support tighter handoff quality."
    brief["hooks"][0]["seller_fact_ids"] = ["fact_3"]
    brief["hooks"][0]["confidence_level"] = "high"
    brief["hooks"][0]["evidence_strength"] = "strong"
    brief["hooks"][0]["risk_flags"] = []

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=_source_payload())

    assert "hook_high_confidence_without_seller_proof" in exc_info.value.codes or "hook_strong_evidence_without_seller_proof" in exc_info.value.codes


def test_validate_messaging_brief_rejects_contaminated_research_hook() -> None:
    brief = _base_brief()
    brief["facts_from_input"][0]["text"] = "Blueway Transit expanded RevOps ownership in January 2026."
    brief["facts_from_input"].append(
        {
            "fact_id": "fact_3",
            "source_field": "proof_points",
            "fact_kind": "seller_proof",
            "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
        }
    )
    brief["hooks"][0]["seller_support"] = "A SaaS team reduced handoff delays by 18% after sequence QA reviews."
    brief["hooks"][0]["seller_fact_ids"] = ["fact_3"]
    brief["hooks"][0]["supported_by_fact_ids"] = ["fact_1"]
    brief["hooks"][0]["risk_flags"] = []

    source_payload = _source_payload()
    source_payload["prospect"]["company"] = "Altura Stone"
    source_payload["prospect"]["research_text"] = "Blueway Transit expanded RevOps ownership in January 2026."

    with pytest.raises(ValidationIssue) as exc_info:
        validate_messaging_brief(brief, source_text="Blueway Transit expanded RevOps ownership in January 2026.", source_payload=source_payload)

    assert "hook_contaminated_research" in exc_info.value.codes


def test_validate_messaging_brief_allows_duplicate_fact_text_when_input_duplicates_it() -> None:
    brief = _base_brief()
    brief["facts_from_input"].append(
        {
            "fact_id": "fact_3",
            "source_field": "prospect_notes",
            "fact_kind": "prospect_context",
            "text": "Nimbus expanded RevOps ownership in January 2026.",
        }
    )
    source_payload = _source_payload()
    source_payload["prospect"]["notes"] = "Nimbus expanded RevOps ownership in January 2026."

    validate_messaging_brief(brief, source_text="Nimbus expanded RevOps ownership in January 2026.", source_payload=source_payload)
