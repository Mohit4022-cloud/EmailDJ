from __future__ import annotations

from app.engine.brief_honesty import hook_has_strong_claim_language
from app.engine.stage_a_sanitizer import sanitize_stage_a_brief


def _source_payload() -> dict:
    return {
        "user_company": {
            "product_summary": "Attribution-Safe QA",
            "icp_description": "RevOps teams",
            "differentiators": ["Evidence lineage checks"],
            "proof_points": ["A SaaS team reduced handoff delays by 18% after sequence QA reviews."],
            "do_not_say": [],
            "company_notes": "Strictly reject facts not attributable to this prospect/company.",
        },
        "prospect": {
            "name": "Nadia Cole",
            "title": "Head of Revenue Operations",
            "company": "Altura Stone",
            "industry": "",
            "notes": "None provided.",
            "research_text": "Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs.",
        },
        "cta": {
            "cta_type": "question",
            "cta_final_line": "Would you be open to a quick attribution-safety walkthrough?",
        },
    }


def test_sanitize_stage_a_brief_removes_placeholder_rows_and_preserves_surviving_ids() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_1",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "company", "fact_kind": "prospect_context", "text": "Altura Stone"},
            {"fact_id": "fact_02", "source_field": "research_text", "fact_kind": "prospect_context", "text": "Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs."},
            {"fact_id": "fact_03", "source_field": "prospect_notes", "fact_kind": "prospect_context", "text": "None provided"},
            {"fact_id": "fact_04", "source_field": "proof_points", "fact_kind": "seller_proof", "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews."},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "initiative",
                "grounded_observation": "Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs.",
                "inferred_relevance": "That may make attribution safety relevant.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Attribution safety may be relevant while RevOps ownership is expanding.",
                "supported_by_fact_ids": ["fact_02", ""],
                "seller_fact_ids": ["fact_04", ""],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": ["", "seller_proof_gap"],
            },
            {
                "hook_id": "hook_02",
                "hook_type": "priority",
                "grounded_observation": "Unknown",
                "inferred_relevance": "None provided",
                "seller_support": "/",
                "hook_text": "This hook should disappear.",
                "supported_by_fact_ids": [""],
                "seller_fact_ids": [],
                "confidence_level": "low",
                "evidence_strength": "weak",
                "risk_flags": [],
            },
        ],
        "persona_cues": {
            "likely_kpis": ["forecast consistency", "Unknown"],
            "likely_initiatives": ["-"],
            "day_to_day": ["pipeline governance"],
            "tools_stack": ["/"],
            "notes": "N/A",
        },
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Blueway Transit expanded RevOps ownership in 2026 to improve handoff SLAs.",
        source_payload=_source_payload(),
    )

    assert [fact["fact_id"] for fact in sanitized["facts_from_input"]] == ["fact_01", "fact_02", "fact_04"]
    assert sanitized["hooks"] == []
    assert sanitized["persona_cues"]["likely_kpis"] == ["forecast consistency"]
    assert sanitized["persona_cues"]["tools_stack"] == []
    assert sanitized["persona_cues"]["notes"] == ""
    assert "fact_03" in report["removed_fact_ids"]
    assert "hook_01" in report["removed_hook_ids"]
    assert "hook_02" in report["removed_hook_ids"]
    assert report["sanitation_changed_semantic_eligibility"] is True
    assert raw_hygiene["raw_artifact_quality"]["status"] == "sloppy"
    assert raw_hygiene["raw_artifact_quality"]["issue_count"] >= 4


def test_sanitize_stage_a_brief_recomputes_derived_fields_after_cleanup() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_2",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "company", "fact_kind": "prospect_context", "text": "Altura Stone"},
            {"fact_id": "fact_02", "source_field": "research_text", "fact_kind": "prospect_context", "text": "-"},
            {"fact_id": "fact_03", "source_field": "proof_points", "fact_kind": "seller_proof", "text": "A SaaS team reduced handoff delays by 18% after sequence QA reviews."},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "initiative",
                "grounded_observation": "Altura Stone is expanding RevOps ownership.",
                "inferred_relevance": "That may make attribution safety relevant.",
                "seller_support": "A SaaS team reduced handoff delays by 18% after sequence QA reviews.",
                "hook_text": "Attribution safety may be timely.",
                "supported_by_fact_ids": ["fact_02"],
                "seller_fact_ids": ["fact_03"],
                "confidence_level": "high",
                "evidence_strength": "strong",
                "risk_flags": [],
            }
        ],
        "persona_cues": {
            "likely_kpis": [],
            "likely_initiatives": [],
            "day_to_day": [],
            "tools_stack": [],
            "notes": "",
        },
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, _raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="No verifiable external research provided.",
        source_payload=_source_payload(),
    )

    assert all(fact["fact_id"] != "fact_02" for fact in sanitized["facts_from_input"])
    assert sanitized["brief_quality"]["signal_strength"] == "medium"
    assert sanitized["brief_quality"]["overreach_risk"] == "low"
    assert report["before"]["fact_count"] > report["after"]["fact_count"]


def test_sanitize_stage_a_brief_caps_unearned_hook_confidence_and_adds_gap_flag() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_3",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "company", "fact_kind": "prospect_context", "text": "Nimbus Forge"},
            {
                "fact_id": "fact_02",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
            },
            {"fact_id": "fact_03", "source_field": "product_summary", "fact_kind": "seller_context", "text": "Outbound Workflow QA"},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "grounded_observation": "Nimbus Forge launched a January 2026 RevOps quality program.",
                "inferred_relevance": "That may make handoff quality relevant.",
                "seller_support": "",
                "hook_text": "As VP Revenue Operations, you likely prioritize forecast reliability; our sequence QA can help reduce handoff issues.",
                "supported_by_fact_ids": ["fact_02"],
                "seller_fact_ids": ["fact_03"],
                "confidence_level": "high",
                "evidence_strength": "strong",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, _raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
        source_payload={
            "user_company": {
                "product_summary": "Outbound Workflow QA",
                "proof_points": [],
            },
            "prospect": {
                "company": "Nimbus Forge",
                "research_text": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
            },
            "cta": {},
        },
    )

    hook = sanitized["hooks"][0]
    assert hook["confidence_level"] == "medium"
    assert hook["evidence_strength"] == "moderate"
    assert hook["risk_flags"] == ["seller_proof_gap"]
    assert report["sanitation_action_counts"]["cap_hook_confidence_level"] == 1
    assert report["sanitation_action_counts"]["cap_hook_evidence_strength"] == 1
    assert report["sanitation_action_counts"]["add_hook_required_risk_flag"] == 1
    assert "hook_support_posture" in report["semantic_change_reasons"]


def test_sanitize_stage_a_brief_softens_unearned_strong_hook_claims() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_strong_claim",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "product_summary", "fact_kind": "seller_context", "text": "EmailDJ"},
            {
                "fact_id": "fact_02",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
            },
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "grounded_observation": "Lattice Harbor is trying to reduce outbound inconsistency.",
                "inferred_relevance": "That may make enablement quality relevant.",
                "seller_support": "EmailDJ constrains sparse context before drafting.",
                "hook_text": "I noticed Lattice Harbor is focused on consistency in outbound for new hires - would you be open to a quick chat?",
                "supported_by_fact_ids": ["fact_02"],
                "seller_fact_ids": ["fact_01"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, _raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
        source_payload={
            "user_company": {"product_summary": "EmailDJ"},
            "prospect": {
                "company": "Lattice Harbor",
                "research_text": "Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
            },
            "cta": {},
        },
    )

    hook = sanitized["hooks"][0]
    assert "is focused on" not in hook["hook_text"].lower()
    assert "may be working on consistency" in hook["hook_text"]
    assert hook_has_strong_claim_language(hook) is False
    assert report["sanitation_action_counts"]["soften_hook_unearned_strong_claim"] == 1
    assert "hook_support_posture" in report["semantic_change_reasons"]


def test_sanitize_stage_a_brief_repairs_hook_references_to_surviving_research_fact() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_3b",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "company", "fact_kind": "prospect_context", "text": "Nimbus Forge"},
            {
                "fact_id": "fact_02",
                "source_field": "prospect_notes",
                "fact_kind": "prospect_context",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
            },
            {
                "fact_id": "fact_03",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
            },
            {"fact_id": "fact_04", "source_field": "product_summary", "fact_kind": "seller_context", "text": "Outbound Workflow QA"},
            {
                "fact_id": "fact_05",
                "source_field": "proof_points",
                "fact_kind": "seller_proof",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
            },
            {
                "fact_id": "fact_06",
                "source_field": "differentiators",
                "fact_kind": "seller_context",
                "text": "Sequence QA scoring",
            },
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "grounded_observation": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
                "inferred_relevance": "That may make handoff quality and forecast reliability more relevant.",
                "seller_support": "Sequence QA scoring and handoff alerts support that workflow.",
                "hook_text": "Nimbus Forge's quality program may make outbound QA discipline timely.",
                "supported_by_fact_ids": ["fact_04", "fact_05", "fact_02"],
                "seller_fact_ids": ["fact_04", "fact_06", "fact_05"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, _raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
        source_payload={
            "user_company": {
                "product_summary": "Outbound Workflow QA",
                "differentiators": ["Sequence QA scoring"],
                "proof_points": [],
            },
            "prospect": {
                "company": "Nimbus Forge",
                "research_text": "Nimbus Forge launched a January 2026 RevOps quality program with handoff SLA targets.",
            },
            "cta": {},
        },
    )

    assert [fact["fact_id"] for fact in sanitized["facts_from_input"]] == ["fact_01", "fact_03", "fact_04", "fact_06"]
    assert [hook["hook_id"] for hook in sanitized["hooks"]] == ["hook_01"]
    assert sanitized["hooks"][0]["supported_by_fact_ids"] == ["fact_04", "fact_03"]
    assert sanitized["hooks"][0]["seller_fact_ids"] == ["fact_04", "fact_06"]
    assert report["sanitation_action_counts"]["repair_hook_fact_reference"] == 2


def test_sanitize_stage_a_brief_drops_field_label_placeholders_and_unbacked_seller_support() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_4",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "company", "fact_kind": "prospect_context", "text": "Pillar Circuit"},
            {"fact_id": "fact_02", "source_field": "prospect_notes", "fact_kind": "prospect_context", "text": "prospect_notes:"},
            {"fact_id": "fact_03", "source_field": "industry", "fact_kind": "prospect_context", "text": "(blank)"},
            {"fact_id": "fact_04", "source_field": "research_text", "fact_kind": "prospect_context", "text": "Pillar Circuit launched a workflow audit in February 2026."},
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "priority",
                "grounded_observation": "VP Revenue Operations at Pillar Circuit.",
                "inferred_relevance": "Role-based relevance.",
                "seller_support": "Role-based relevance.",
                "hook_text": "As a RevOps leader, workflow QA could matter.",
                "supported_by_fact_ids": ["fact_01", "fact_04"],
                "seller_fact_ids": [],
                "confidence_level": "low",
                "evidence_strength": "weak",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Pillar Circuit launched a workflow audit in February 2026.",
        source_payload={
            "user_company": {},
            "prospect": {"company": "Pillar Circuit", "research_text": "Pillar Circuit launched a workflow audit in February 2026."},
            "cta": {},
        },
    )

    assert [fact["fact_id"] for fact in sanitized["facts_from_input"]] == ["fact_01", "fact_04"]
    assert sanitized["hooks"][0]["seller_support"] == ""
    assert report["sanitation_action_counts"]["normalize_hook_unbacked_seller_support"] == 1
    assert raw_hygiene["raw_artifact_quality"]["issue_count"] >= 3


def test_sanitize_stage_a_brief_drops_source_without_input_signal_and_same_source_duplicates() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_5",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "company", "fact_kind": "prospect_context", "text": "Nimbus Forge"},
            {
                "fact_id": "fact_02",
                "source_field": "prospect_notes",
                "fact_kind": "prospect_context",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program.",
            },
            {
                "fact_id": "fact_03",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program.",
            },
            {
                "fact_id": "fact_04",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Nimbus Forge launched a January 2026 RevOps quality program.",
            },
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "initiative",
                "grounded_observation": "Nimbus Forge launched a January 2026 RevOps quality program.",
                "inferred_relevance": "That may make consistency work timely.",
                "seller_support": "",
                "hook_text": "Consistency work may be timely.",
                "supported_by_fact_ids": ["fact_02", "fact_03", "fact_04"],
                "seller_fact_ids": [],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Nimbus Forge launched a January 2026 RevOps quality program.",
        source_payload={
            "user_company": {},
            "prospect": {"company": "Nimbus Forge", "research_text": "Nimbus Forge launched a January 2026 RevOps quality program."},
            "cta": {},
        },
    )

    assert [fact["fact_id"] for fact in sanitized["facts_from_input"]] == ["fact_01", "fact_03"]
    assert sanitized["hooks"][0]["supported_by_fact_ids"] == ["fact_03"]
    assert report["sanitation_action_counts"]["drop_fact_source_without_input_signal"] == 1
    assert report["sanitation_action_counts"]["drop_fact_duplicate_text_same_kind"] == 1
    assert report["sanitation_action_counts"]["drop_hook_missing_fact_reference"] == 1
    assert raw_hygiene["raw_artifact_quality"]["issue_count"] >= 2


def test_sanitize_stage_a_brief_drops_same_kind_duplicate_even_across_sources() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_6",
        "facts_from_input": [
            {
                "fact_id": "fact_01",
                "source_field": "company_notes",
                "fact_kind": "seller_context",
                "text": "EmailDJ translates sparse context into constrained atoms before drafting.",
            },
            {
                "fact_id": "fact_02",
                "source_field": "product_summary",
                "fact_kind": "seller_context",
                "text": "EmailDJ translates sparse context into constrained atoms before drafting.",
            },
            {
                "fact_id": "fact_03",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
            },
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "grounded_observation": "Lattice Harbor is trying to reduce outbound inconsistency.",
                "inferred_relevance": "That may make draft QA relevant for enablement.",
                "seller_support": "EmailDJ translates sparse context into constrained atoms before drafting.",
                "hook_text": "Outbound inconsistency may make constrained draft QA relevant.",
                "supported_by_fact_ids": ["fact_03"],
                "seller_fact_ids": ["fact_02"],
                "confidence_level": "medium",
                "evidence_strength": "moderate",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, _raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
        source_payload={
            "user_company": {
                "product_summary": "EmailDJ",
                "company_notes": "EmailDJ translates sparse context into constrained atoms before drafting.",
            },
            "prospect": {
                "company": "Lattice Harbor",
                "research_text": "Lattice Harbor is trying to reduce outbound inconsistency across new-hire cohorts.",
            },
            "cta": {},
        },
    )

    assert [fact["fact_id"] for fact in sanitized["facts_from_input"]] == ["fact_01", "fact_03"]
    assert sanitized["hooks"][0]["seller_fact_ids"] == ["fact_01"]
    assert report["sanitation_action_counts"]["drop_fact_duplicate_text_same_kind"] == 1
    assert report["sanitation_action_counts"]["repair_hook_fact_reference"] == 1


def test_sanitize_stage_a_brief_removes_prospect_fact_from_seller_fact_ids() -> None:
    raw_brief = {
        "version": "1.0",
        "brief_id": "brief_7",
        "facts_from_input": [
            {"fact_id": "fact_01", "source_field": "product_summary", "fact_kind": "seller_context", "text": "EmailDJ"},
            {
                "fact_id": "fact_02",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Raven Pilot reported inconsistent opener quality across SDR pods.",
            },
        ],
        "assumptions": [],
        "hooks": [
            {
                "hook_id": "hook_01",
                "hook_type": "pain",
                "grounded_observation": "Raven Pilot reported inconsistent opener quality across SDR pods.",
                "inferred_relevance": "That may make opener quality controls relevant.",
                "seller_support": "Raven Pilot reported inconsistent opener quality across SDR pods.",
                "hook_text": "Inconsistent opener quality may make QA controls relevant.",
                "supported_by_fact_ids": ["fact_02"],
                "seller_fact_ids": ["fact_02"],
                "confidence_level": "high",
                "evidence_strength": "strong",
                "risk_flags": [],
            }
        ],
        "persona_cues": {"likely_kpis": [], "likely_initiatives": [], "day_to_day": [], "tools_stack": [], "notes": ""},
        "do_not_say": [],
        "forbidden_claim_patterns": [],
        "prohibited_overreach": [],
        "grounding_policy": {},
        "brief_quality": {"quality_notes": []},
    }

    sanitized, report, _raw_hygiene = sanitize_stage_a_brief(
        raw_brief,
        source_text="Raven Pilot reported inconsistent opener quality across SDR pods.",
        source_payload={
            "user_company": {"product_summary": "EmailDJ"},
            "prospect": {
                "company": "Raven Pilot",
                "research_text": "Raven Pilot reported inconsistent opener quality across SDR pods.",
            },
            "cta": {},
        },
    )

    hook = sanitized["hooks"][0]
    assert hook["seller_fact_ids"] == []
    assert hook["seller_support"] == ""
    assert hook["risk_flags"] == ["seller_proof_gap"]
    assert hook["confidence_level"] == "medium"
    assert hook["evidence_strength"] == "moderate"
    assert report["sanitation_action_counts"]["drop_hook_non_seller_fact_reference"] == 1
    assert report["sanitation_action_counts"]["normalize_hook_unbacked_seller_support"] == 1
