from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import uuid4

from app.config import load_settings
from app.engine.ai_orchestrator import AIOrchestrator
from app.engine.brief_cache import BriefCache
from app.engine.tracer import Trace
from app.engine.validators import PROOF_GAP_TEXT, build_cta_lock, opener_contract
from app.schemas import WebCompanyContext, WebGenerateRequest, WebProspectInput, WebSliders, WebStyleProfile


CTA = "Open to a quick chat to see if this is relevant?"


class StubOpenAI:
    def __init__(self, responses: list[Any]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def enabled(self) -> bool:
        return True

    async def chat_completion(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        payload = self.responses.pop(0) if self.responses else {}
        if isinstance(payload, str):
            content = payload
        else:
            content = json.dumps(payload)
        return {"message": {"content": content}, "usage": {}}


def _request() -> WebGenerateRequest:
    return WebGenerateRequest(
        prospect=WebProspectInput(
            name="Alex Doe",
            title="Head of RevOps",
            company="Acme",
            company_url="https://acme.example",
            linkedin_url="https://linkedin.com/in/alex",
        ),
        prospect_first_name="Alex",
        research_text="Acme announced a RevOps pipeline initiative focused on workflow consistency.",
        offer_lock="Remix Studio",
        cta_offer_lock=CTA,
        cta_type="question",
        preset_id="direct",
        response_contract="email_json_v1",
        mode="single",
        sliders=WebSliders(tone=0.5, framing=0.5, length="short", stance=0.5),
        style_profile=WebStyleProfile(formality=0.0, orientation=0.0, length=-0.7, assertiveness=0.0),
        company_context=WebCompanyContext(
            company_name="Example Seller",
            current_product="Remix Studio",
            seller_offerings="Workflow QA\nExecution analytics",
            internal_modules="Prospect Enrichment\nSequence QA",
            company_notes="Supports GTM teams with repeatable messaging workflows.",
            cta_offer_lock=CTA,
            cta_type="question",
        ),
    )


def _brief() -> dict[str, Any]:
    return {
        "version": "1",
        "brief_id": "brief_1",
        "facts_from_input": [
            {
                "fact_id": "fact_1",
                "source_field": "research_text",
                "fact_kind": "prospect_context",
                "text": "Acme announced a RevOps initiative.",
            },
        ],
        "assumptions": [
            {
                "assumption_id": "assump_1",
                "assumption_kind": "inferred_hypothesis",
                "text": "Ops leadership may want consistency",
                "confidence": 0.6,
                "confidence_label": "medium",
                "based_on_fact_ids": ["fact_1"],
            }
        ],
        "hooks": [
            {
                "hook_id": "hook_1",
                "hook_type": "initiative",
                "grounded_observation": "Acme announced a RevOps initiative.",
                "inferred_relevance": "That may mean workflow consistency is being reviewed.",
                "seller_support": "",
                "hook_text": "Acme's RevOps initiative may make consistency conversations timely.",
                "supported_by_fact_ids": ["fact_1"],
                "seller_fact_ids": [],
                "confidence_level": "medium",
                "evidence_strength": "weak",
                "risk_flags": ["seller_proof_gap"],
            }
        ],
        "hook_lineage": {
            "canonical_hook_ids": ["hook_1"],
            "hook_alias_map": {"hook_1": "hook_1", "legacy_hook_1": "hook_1"},
        },
        "persona_cues": {
            "likely_kpis": ["pipeline coverage"],
            "likely_initiatives": ["workflow consistency"],
            "day_to_day": ["manage sequence quality"],
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
            "quality_notes": [],
        },
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


def _fit_map() -> dict[str, Any]:
    return {
        "version": "1",
        "hypotheses": [
            {
                "fit_hypothesis_id": "fit_1",
                "rank": 1,
                "selected_hook_id": "hook_1",
                "pain": "inconsistent outbound execution",
                "impact": "lower conversion",
                "value": "repeatable outreach quality",
                "proof": "workflow QA controls",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="workflow QA controls",
                ),
                "supporting_fact_ids": ["fact_1"],
                "why_now": "initiative timing",
                "confidence": 0.8,
                "risk_flags": [],
            }
        ],
    }


def _angles() -> dict[str, Any]:
    return {
        "version": "1",
        "angles": [
            {
                "angle_id": "angle_1",
                "angle_type": "problem_led",
                "rank": 1,
                "persona_fit_score": 0.9,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "inconsistent outreach",
                "impact": "conversion drag",
                "value": "repeatable quality",
                "proof": "workflow QA",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="workflow QA",
                ),
                "primary_pain": "inconsistent outreach",
                "primary_value_motion": "repeatable quality",
                "primary_proof_basis": "capability_statement|workflow_qa",
                "framing_type": "problem_led",
                "risk_level": "low",
                "cta_question_suggestion": "quick review",
                "risk_flags": [],
            },
            {
                "angle_id": "angle_2",
                "angle_type": "outcome_led",
                "rank": 2,
                "persona_fit_score": 0.8,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "execution noise",
                "impact": "slower pipeline",
                "value": "faster iteration",
                "proof": "workflow QA",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="workflow QA",
                ),
                "primary_pain": "execution noise",
                "primary_value_motion": "faster iteration",
                "primary_proof_basis": "capability_statement|workflow_qa|iteration",
                "framing_type": "outcome_led",
                "risk_level": "medium",
                "cta_question_suggestion": "quick review",
                "risk_flags": [],
            },
            {
                "angle_id": "angle_3",
                "angle_type": "proof_led",
                "rank": 3,
                "persona_fit_score": 0.7,
                "selected_hook_id": "hook_1",
                "selected_fit_hypothesis_id": "fit_1",
                "pain": "manual drift",
                "impact": "reply drop",
                "value": "consistent controls",
                "proof": "workflow QA",
                "proof_basis": _proof_basis(
                    kind="capability_statement",
                    source_text="workflow QA",
                ),
                "primary_pain": "manual drift",
                "primary_value_motion": "consistent controls",
                "primary_proof_basis": "capability_statement|workflow_qa|controls",
                "framing_type": "proof_led",
                "risk_level": "medium",
                "cta_question_suggestion": "quick review",
                "risk_flags": [],
            },
        ],
    }


def _atoms() -> dict[str, Any]:
    return _atoms_for("direct")


def _atoms_for(
    preset_id: str,
    *,
    proof_atom: str | None = None,
    target_word_budget: int | None = None,
    target_sentence_budget: int | None = None,
) -> dict[str, Any]:
    resolved_target_word_budget = target_word_budget
    if resolved_target_word_budget is None:
        resolved_target_word_budget = {
            "direct": 51,
            "challenger": 61,
            "storyteller": 60,
        }.get(str(preset_id), 51)
    resolved_proof_atom = "" if proof_atom is None else proof_atom
    resolved_target_sentence_budget = target_sentence_budget
    if resolved_target_sentence_budget is None:
        resolved_target_sentence_budget = 3 if resolved_proof_atom.strip() == "" else 4
    resolved_proof_basis = (
        _proof_basis(kind="none", source_text="", proof_gap=True)
        if resolved_proof_atom.strip() == ""
        else _proof_basis(kind="capability_statement", source_text=resolved_proof_atom)
    )
    return {
        "version": "1",
        "preset_id": preset_id,
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "canonical_hook_ids": ["hook_1"],
        "opener_atom": "Noticed Acme is prioritizing RevOps workflow consistency.",
        "opener_line": "Noticed Acme is prioritizing RevOps workflow consistency.",
        "opener_contract": opener_contract(),
        "value_atom": "Teams usually improve meeting quality when messaging execution is consistent.",
        "proof_atom": resolved_proof_atom,
        "proof_basis": resolved_proof_basis,
        "cta_atom": CTA,
        "cta_intent": "Ask whether a quick chat is relevant.",
        "required_cta_line": CTA,
        "cta_lock": build_cta_lock(CTA),
        "target_word_budget": resolved_target_word_budget,
        "target_sentence_budget": resolved_target_sentence_budget,
    }


def _rewrite_patch(
    *,
    preset_id: str = "direct",
    text_by_index: dict[int, str] | None = None,
    insert_after: dict[int, str] | None = None,
    delete_indexes: list[int] | None = None,
    preserve_indexes: list[int] | None = None,
) -> dict[str, Any]:
    sentence_operations: list[dict[str, Any]] = []
    for index, text in sorted((text_by_index or {}).items()):
        sentence_operations.append(
            {
                "issue_code": "other",
                "action": "rewrite",
                "target_sentence_index": index,
                "text": text,
            }
        )
    for index, text in sorted((insert_after or {}).items()):
        sentence_operations.append(
            {
                "issue_code": "word_count_out_of_band",
                "action": "insert_after",
                "target_sentence_index": index,
                "text": text,
            }
        )
    for index in sorted(delete_indexes or []):
        sentence_operations.append(
            {
                "issue_code": "other",
                "action": "delete",
                "target_sentence_index": index,
                "text": "",
            }
        )
    return {
        "version": "1",
        "preset_id": preset_id,
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "cta_lock": build_cta_lock(CTA),
        "preserve_sentence_indexes": list(preserve_indexes or []),
        "sentence_operations": sentence_operations,
    }


def _valid_draft(preset_id: str = "direct") -> dict[str, Any]:
    body = (
        "Hi Alex,\n\n"
        "Acme's RevOps initiative suggests your team is tightening workflow consistency. "
        "We help teams reduce sequence drift and improve meeting quality with practical QA controls. "
        "This keeps messaging specific and repeatable without extra overhead.\n\n"
        f"{CTA}"
    )
    return {
        "version": "1",
        "preset_id": preset_id,
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "subject": "RevOps workflow consistency idea",
        "body": body,
    }


def _qa(pass_rewrite_needed: bool = False) -> dict[str, Any]:
    return {
        "version": "1",
        "pass_rewrite_needed": pass_rewrite_needed,
        "issues": [],
        "risk_flags": [],
        "rewrite_plan": [],
    }


def _qa_with_issue(
    issue_type: str,
    *,
    severity: str = "high",
    evidence_quote: str = "Acme's RevOps initiative suggests your team is tightening workflow consistency.",
) -> dict[str, Any]:
    legacy_type = issue_type if issue_type in {
        "credibility",
        "specificity",
        "structure",
        "spam_risk",
        "personalization",
        "length",
        "cta",
        "grammar",
        "tone",
        "clarity",
        "word_count_out_of_band",
        "opener_too_soft_for_preset",
        "proof_density_too_low",
        "too_many_sentences_for_preset",
        "tone_mismatch_for_preset",
        "cta_not_in_expected_form",
        "other",
    } else "other"
    return {
        "version": "1",
        "pass_rewrite_needed": True,
        "issues": [
            {
                "issue_code": issue_type,
                "type": legacy_type,
                "severity": severity,
                "offending_span_or_target_section": evidence_quote,
                "evidence_quote": evidence_quote,
                "why_it_fails": "The quoted opener needs a tighter, grounded rewrite for the active preset contract.",
                "evidence": [evidence_quote],
                "fix_instruction": "Replace the opener sentence with a tighter grounded opener and keep the locked CTA line unchanged.",
                "expected_effect": "Restore grounded preset fit without changing untouched lines.",
            }
        ],
        "risk_flags": [],
        "rewrite_plan": [
            {
                "issue_code": issue_type,
                "target": evidence_quote,
                "action": "Replace the opener sentence with a tighter grounded opener tied to the selected hook.",
                "replacement_guidance": "Use only grounded wording already supported by the brief and keep the locked CTA text unchanged.",
                "preserve": f'Keep the locked CTA text "{CTA}" unchanged and leave unrelated grounded sentences untouched.',
                "expected_effect": "Restore grounded preset fit without changing untouched lines.",
            }
        ],
    }


def _orchestrator(responses: list[Any]) -> AIOrchestrator:
    settings = replace(load_settings(), app_env="test")
    return AIOrchestrator(openai=StubOpenAI(responses), settings=settings, brief_cache=BriefCache())


def _extract_context_json_from_user_prompt(content: str) -> dict[str, Any]:
    marker = "CONTEXT JSON:\\n"
    start = content.index(marker) + len(marker)
    end = content.rfind("\\n\\nOutput")
    return json.loads(content[start:end])


def test_atoms_sanitizer_repairs_bracket_placeholder_slots() -> None:
    orchestrator = _orchestrator([])
    brief = _brief()
    brief["facts_from_input"].append(
        {
            "fact_id": "fact_title",
            "source_field": "title",
            "fact_kind": "prospect_context",
            "text": "Head of RevOps",
        }
    )
    atoms = _atoms_for("direct")
    atoms["opener_atom"] = "[Prospect] is trying to improve outbound consistency."
    atoms["opener_line"] = "[Prospect] is trying to improve outbound consistency."
    atoms["value_atom"] = "[Persona's team] gains [specific capability] without [specific cost or tradeoff]."

    sanitized, metadata = orchestrator._sanitize_message_atoms_payload(
        atoms,
        preset_id="direct",
        selected_angle=_angles()["angles"][0],
        cta_line=CTA,
        messaging_brief=brief,
        budget_plan={"target_total_words": 51},
    )

    actions = metadata["atom_sanitation_report"]["actions"]
    assert "repair_atoms_placeholder_opener_atom" in actions
    assert "repair_atoms_placeholder_value_atom" in actions
    assert "[" not in sanitized["opener_atom"]
    assert "[" not in sanitized["opener_line"]
    assert "[" not in sanitized["value_atom"]
    assert sanitized["opener_line"] == sanitized["opener_atom"]
    assert sanitized["value_atom"] == "RevOps teams tighten message quality without adding review drag."
    assert sanitized["target_sentence_budget"] == 3


def test_atoms_sanitizer_repairs_mechanism_only_value_atom() -> None:
    orchestrator = _orchestrator([])
    atoms = _atoms_for("direct")
    atoms["value_atom"] = "Teams use workflow QA and scoring for outbound process reviews."

    sanitized, metadata = orchestrator._sanitize_message_atoms_payload(
        atoms,
        preset_id="direct",
        selected_angle=_angles()["angles"][0],
        cta_line=CTA,
        messaging_brief=_brief(),
        budget_plan={"target_total_words": 51},
    )

    actions = metadata["atom_sanitation_report"]["actions"]
    assert "repair_atoms_mechanism_value_atom" in actions
    assert sanitized["value_atom"] == "Teams tighten message quality without adding review drag."


def test_stage_a_invalid_json_fails_closed_no_subject_body() -> None:
    req = _request()
    orchestrator = _orchestrator([{}, {}])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is False
    assert result.subject is None
    assert result.body is None
    assert result.error
    assert result.error["stage"] == "CONTEXT_SYNTHESIS"


def test_stage_e_final_validation_failure_is_fail_closed() -> None:
    req = _request()
    bad_draft = _valid_draft()
    bad_draft["body"] = bad_draft["body"].replace("practical QA controls", "touch base on practical QA controls")

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        bad_draft,
        _qa(pass_rewrite_needed=False),
        bad_draft,
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is False
    assert result.subject is None
    assert result.body is None
    assert result.error
    assert result.error["stage"] == "EMAIL_REWRITE"


def test_message_atoms_repair_recovers_one_cta_mismatch_case() -> None:
    req = _request()
    bad_atoms = _atoms()
    bad_atoms["cta_atom"] = "Would you be open to a call next week?"

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        bad_atoms,
        _atoms(),
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is True
    atom_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "ONE_LINER_COMPRESSOR" and item.get("status") == "complete"]
    assert atom_entries[-1]["attempt_count"] == 1
    assert atom_entries[-1]["final_validation_status"] == "passed"
    assert atom_entries[-1]["cta_alignment_status"] == "aligned"


def test_preset_browse_returns_mixed_success_and_error_variants() -> None:
    req = _request().model_copy(update={"mode": "preset_browse", "preset_ids": ["direct", "challenger"]})
    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        _valid_draft("direct"),
        _qa(pass_rewrite_needed=False),
        _atoms_for("challenger"),
        {},
        {},
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(
        orchestrator.run_pipeline_presets(
            request=req,
            trace=trace,
            preset_ids=["direct", "challenger"],
            sliders=req.sliders.model_dump(),
        )
    )

    assert result.ok is True
    assert isinstance(result.variants, list)
    assert len(result.variants) == 2
    assert "subject" in result.variants[0]
    assert result.variants[1].get("error")
    traced_stages = {str(item.get("stage") or "") for item in result.stage_stats}
    assert "EMAIL_GENERATION:direct" in traced_stages
    assert "EMAIL_GENERATION:challenger" in traced_stages
    assert "EMAIL_QA:direct" in traced_stages


def test_cta_lock_mechanical_postprocess_preserves_exact_final_line() -> None:
    orchestrator = _orchestrator([])
    trace = Trace(str(uuid4()), "test")
    wrong_cta_draft = _valid_draft()
    wrong_cta_draft["body"] = wrong_cta_draft["body"].replace(CTA, "Can we connect this week?")

    repaired, _ = orchestrator._mechanical_postprocess(  # noqa: SLF001
        wrong_cta_draft,
        {"tone": 0.5, "framing": 0.5, "length": "short", "stance": 0.5},
        CTA,
        trace,
        budget_plan=None,
    )

    assert repaired["body"].rstrip().endswith(CTA)
    assert repaired["body"].count(CTA) == 1


def test_empty_proof_atom_is_normalized_before_stage_c() -> None:
    req = _request()
    atoms_without_proof = _atoms_for("direct", proof_atom="   ")

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        atoms_without_proof,
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert isinstance(orchestrator.openai, StubOpenAI)
    email_calls = [
        call
        for call in orchestrator.openai.calls
        if call.get("response_format", {}).get("json_schema", {}).get("name") == "EmailDraft"
    ]
    assert len(email_calls) == 1

    context = _extract_context_json_from_user_prompt(email_calls[0]["messages"][1]["content"])
    message_atoms = dict(context.get("message_atoms") or {})
    assert message_atoms["proof_atom"] == ""
    assert context["budget_plan"]["target_total_words"] == 51


def test_duplicate_hook_ids_and_unsupported_proof_are_sanitized_before_stage_c() -> None:
    req = _request()
    dirty_atoms = _atoms_for(
        "direct",
        proof_atom="A peer team improved forecast accuracy after adopting outbound QA.",
    )
    dirty_atoms["used_hook_ids"] = ["hook_1", "hook_1"]

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        dirty_atoms,
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert isinstance(orchestrator.openai, StubOpenAI)
    email_calls = [
        call
        for call in orchestrator.openai.calls
        if call.get("response_format", {}).get("json_schema", {}).get("name") == "EmailDraft"
    ]
    assert len(email_calls) == 1

    context = _extract_context_json_from_user_prompt(email_calls[0]["messages"][1]["content"])
    message_atoms = dict(context.get("message_atoms") or {})
    assert message_atoms["used_hook_ids"] == ["hook_1"]
    assert message_atoms["proof_atom"] == ""
    assert message_atoms["target_sentence_budget"] == 3


def test_brief_cache_hit_skips_stage_a_b_b0_on_second_request() -> None:
    req = _request()
    cache = BriefCache()
    settings = replace(load_settings(), app_env="test")
    stub = StubOpenAI([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
        _atoms(),
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
        _valid_draft(),
    ])
    orchestrator = AIOrchestrator(openai=stub, settings=settings, brief_cache=cache)

    trace1 = Trace(str(uuid4()), "test")
    first = run(orchestrator.run_pipeline_single(request=req, trace=trace1, preset_id="direct", sliders=req.sliders.model_dump()))
    assert first.ok is True

    trace2 = Trace(str(uuid4()), "test")
    second = run(orchestrator.run_pipeline_single(request=req, trace=trace2, preset_id="direct", sliders=req.sliders.model_dump()))
    assert second.ok is True

    second_stages = {str(item.get("stage")) for item in second.stage_stats if item.get("status") == "started"}
    assert "CONTEXT_SYNTHESIS" not in second_stages
    assert "FIT_REASONING" not in second_stages
    assert "ANGLE_PICKER" not in second_stages


def test_preset_browse_applies_per_preset_slider_overrides_without_rebuilding_brief_stack() -> None:
    req = _request().model_copy(update={"mode": "preset_browse", "preset_ids": ["direct", "challenger"]})
    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        _valid_draft("direct"),
        _qa(pass_rewrite_needed=False),
        _atoms_for("challenger", target_word_budget=145),
        _valid_draft("challenger"),
        _qa(pass_rewrite_needed=False),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(
        orchestrator.run_pipeline_presets(
            request=req,
            trace=trace,
            preset_ids=["direct", "challenger"],
            sliders=req.sliders.model_dump(),
            preset_sliders={
                "direct": {"tone": 0.45, "framing": 0.25, "length": "short", "stance": 0.35},
                "challenger": {"tone": 0.65, "framing": 0.8, "length": "long", "stance": 0.9},
            },
        )
    )

    assert result.ok is True
    assert isinstance(orchestrator.openai, StubOpenAI)
    email_calls = [
        call
        for call in orchestrator.openai.calls
        if call.get("response_format", {}).get("json_schema", {}).get("name") == "EmailDraft"
        and "Senior SDR writing one outbound email" in str(call.get("messages", [{}])[0].get("content") or "")
    ]
    assert len(email_calls) == 2

    first_context = _extract_context_json_from_user_prompt(email_calls[0]["messages"][1]["content"])
    second_context = _extract_context_json_from_user_prompt(email_calls[1]["messages"][1]["content"])

    assert first_context["slider_rules"]["length"] == "short"
    assert second_context["slider_rules"]["length"] == "long"
    assert first_context["preset"]["preset_id"] == "direct"
    assert second_context["preset"]["preset_id"] == "challenger"
    assert first_context["preset_contract"]["length"] == "short"
    assert second_context["preset_contract"]["length"] == "long"
    assert first_context["budget_plan"]["target_total_words"] == 51
    assert second_context["budget_plan"]["target_total_words"] == 145

    stage_starts = [str(item.get("stage") or "") for item in result.stage_stats if item.get("status") == "started"]
    assert stage_starts.count("CONTEXT_SYNTHESIS") == 1
    assert stage_starts.count("FIT_REASONING") == 1
    assert stage_starts.count("ANGLE_PICKER") == 1
    assert stage_starts.count("ONE_LINER_COMPRESSOR:direct") == 1
    assert stage_starts.count("ONE_LINER_COMPRESSOR:challenger") == 1


def test_slider_changes_keep_selected_angle_and_hook_ids_stable_on_cached_brief() -> None:
    req = _request()
    cache = BriefCache()
    settings = replace(load_settings(), app_env="test")
    stub = StubOpenAI([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
        _atoms(),
        _valid_draft(),
        _qa(pass_rewrite_needed=False),
        _valid_draft(),
    ])
    orchestrator = AIOrchestrator(openai=stub, settings=settings, brief_cache=cache)

    first_trace = Trace(str(uuid4()), "test")
    first = run(
        orchestrator.run_pipeline_single(
            request=req,
            trace=first_trace,
            preset_id="direct",
            sliders={"tone": 0.4, "framing": 0.25, "length": "short", "stance": 0.35},
        )
    )
    assert first.ok is True
    assert first.provenance == {
        "preset_id": "direct",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "rewrite_applied": False,
    }

    second_trace = Trace(str(uuid4()), "test")
    second = run(
        orchestrator.run_pipeline_single(
            request=req,
            trace=second_trace,
            preset_id="direct",
            sliders={"tone": 0.65, "framing": 0.6, "length": "short", "stance": 0.85},
        )
    )
    assert second.ok is True
    assert second.provenance["selected_angle_id"] == first.provenance["selected_angle_id"]
    assert second.provenance["used_hook_ids"] == first.provenance["used_hook_ids"]

    second_stages = {str(item.get("stage")) for item in second.stage_stats if item.get("status") == "started"}
    assert "CONTEXT_SYNTHESIS" not in second_stages
    assert "FIT_REASONING" not in second_stages
    assert "ANGLE_PICKER" not in second_stages


def test_qa_rewrite_tightens_weak_draft_and_marks_rewrite_applied() -> None:
    req = _request()
    weak_draft = _valid_draft()
    weak_draft["body"] = (
        "Hi Alex,\n\n"
        "Acme's RevOps initiative may matter. "
        "We help teams improve things in a lot of ways and drive better workflows overall. "
        "It can be very helpful for teams that want more consistency and results.\n\n"
        f"{CTA}"
    )
    rewritten = _valid_draft()

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        weak_draft,
        _qa_with_issue(
            "ungrounded_personalization_claim",
            evidence_quote="Acme's RevOps initiative may matter.",
        ),
        _rewrite_patch(
            text_by_index={
                0: "Hi Alex, Acme's RevOps initiative suggests your team is tightening workflow consistency.",
                1: "We help teams reduce sequence drift and improve meeting quality with practical QA controls.",
                2: "This keeps messaging specific and repeatable without extra overhead.",
            },
        ),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert result.body != weak_draft["body"]
    assert "practical QA controls" in result.body
    assert result.provenance == {
        "preset_id": "direct",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "rewrite_applied": True,
    }
    rewrite_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_REWRITE" and item.get("status") == "complete"]
    assert rewrite_entries
    assert rewrite_entries[-1]["final_validation_status"] == "passed"


def test_challenger_salvage_rescues_slightly_over_band_and_preserves_metadata() -> None:
    req = _request().model_copy(update={"preset_id": "challenger"})
    over_band = _valid_draft("challenger")
    over_band["body"] = (
        "Hi Alex,\n\n"
        "Most RevOps teams do not notice workflow drift until it starts cutting response quality across sequences. "
        "That usually turns routine inspection into reactive cleanup and wasted manager time. "
        "We help teams diagnose that drift earlier, keep the operating point visible, and tighten outbound QA before reply quality falls across reps and handoffs. "
        "A focused workflow QA program gives ops leaders a cleaner way to challenge the status quo without adding extra review overhead or another dashboard to babysit.\n\n"
        f"{CTA}"
    )
    salvaged = _valid_draft("challenger")
    salvaged["body"] = (
        "Hi Alex,\n\n"
        "Workflow drift often stays hidden until reply quality starts slipping. "
        "We help teams catch that drift earlier and tighten outbound QA before reply quality falls across handoffs. "
        "That gives ops leaders a cleaner way to challenge the status quo without more review overhead.\n\n"
        f"{CTA}"
    )

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms_for("challenger"),
        over_band,
        _qa_with_issue(
            "word_count_out_of_band",
            evidence_quote="Most RevOps teams do not notice workflow drift until it starts cutting response quality across sequences.",
        ),
        _rewrite_patch(
            preset_id="challenger",
            text_by_index={
                0: "Hi Alex, workflow drift often stays hidden until reply quality starts slipping.",
                1: "We help teams catch that drift earlier and tighten outbound QA before reply quality falls across handoffs.",
            },
            insert_after={
                1: "That gives ops leaders a cleaner way to challenge the status quo without more review overhead.",
            },
        ),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="challenger", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert result.body != over_band["body"]
    assert result.body.rstrip().endswith(CTA)
    assert result.body.count(CTA) == 1
    assert result.provenance == {
        "preset_id": "challenger",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "rewrite_applied": True,
    }
    rewrite_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_REWRITE" and item.get("status") == "complete"]
    assert rewrite_entries[-1]["salvage_applied"] is False
    assert rewrite_entries[-1]["salvage_result"] == "not_run"
    assert rewrite_entries[-1]["preset_contract_hash"]
    assert rewrite_entries[-1]["post_rewrite_word_count"] > 0


def test_challenger_salvage_rescues_slightly_under_band() -> None:
    req = _request().model_copy(update={"preset_id": "challenger"})
    too_short = _valid_draft("challenger")
    too_short["body"] = (
        "Hi Alex,\n\n"
        "Acme's RevOps initiative makes hidden workflow drift expensive. "
        "We help teams catch it earlier.\n\n"
        f"{CTA}"
    )
    salvaged = _valid_draft("challenger")
    salvaged["body"] = (
        "Hi Alex,\n\n"
        "Hidden workflow drift gets expensive once reply quality starts slipping. "
        "We help teams catch that drift earlier and tighten outbound QA before managers are forced into cleanup mode. "
        "That gives RevOps a more defensible way to challenge the status quo without adding review drag.\n\n"
        f"{CTA}"
    )

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms_for("challenger"),
        too_short,
        _qa_with_issue(
            "word_count_out_of_band",
            evidence_quote="Acme's RevOps initiative makes hidden workflow drift expensive.",
        ),
        _rewrite_patch(
            preset_id="challenger",
            preserve_indexes=[0, 1],
        ),
        salvaged,
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="challenger", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert result.body != too_short["body"]
    assert result.body.rstrip().endswith(CTA)
    assert "cleanup mode" in result.body
    qa_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_QA" and item.get("status") == "complete"]
    rewrite_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_REWRITE" and item.get("status") == "complete"]
    salvage_entries = [
        item
        for item in result.stage_stats
        if str(item.get("stage") or "").startswith("EMAIL_REWRITE_SALVAGE") and item.get("status") == "complete"
    ]
    assert qa_entries[-1]["pre_rewrite_word_count"] < 46
    assert qa_entries[-1]["dominant_failing_rule"] == "word_count_out_of_band"
    assert rewrite_entries[-1]["salvage_applied"] is True
    assert rewrite_entries[-1]["salvage_result"] == "passed"
    assert salvage_entries[-1]["post_salvage_word_count"] >= 46


def test_qa_heuristics_trigger_rewrite_for_clause_heavy_opener() -> None:
    req = _request()
    generated = _valid_draft()
    generated["body"] = (
        "Hi Alex,\n\n"
        "Because Acme's RevOps initiative is active, and workflow consistency is under review, your team may be feeling sequence drift more sharply. "
        "We help teams reduce sequence drift and improve meeting quality with practical QA controls. "
        "This keeps messaging specific and repeatable without extra overhead.\n\n"
        f"{CTA}"
    )
    rewritten = _valid_draft()
    rewritten["body"] = (
        "Hi Alex,\n\n"
        "Acme's RevOps initiative puts workflow consistency under more scrutiny. "
        "We help teams reduce sequence drift and improve meeting quality with practical QA controls. "
        "This keeps messaging specific and repeatable without extra overhead.\n\n"
        f"{CTA}"
    )

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        generated,
        _qa(pass_rewrite_needed=False),
        _rewrite_patch(
            text_by_index={
                0: "Hi Alex, Acme's RevOps initiative puts workflow consistency under more scrutiny.",
            },
            preserve_indexes=[1, 2],
        ),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert "Because Acme's RevOps initiative is active" not in result.body
    assert "This keeps messaging specific and repeatable without extra overhead." in result.body
    qa_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_QA" and item.get("status") == "complete"]
    assert qa_entries[-1]["dominant_failing_rule"] == "opener_too_complex"
    rewrite_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_REWRITE" and item.get("status") == "complete"]
    assert rewrite_entries


def test_salvage_does_not_run_on_semantic_failure() -> None:
    req = _request().model_copy(update={"preset_id": "challenger"})
    bad_rewrite = _valid_draft("challenger")
    bad_rewrite["body"] = bad_rewrite["body"].replace("practical QA controls", "touch base on practical QA controls")

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms_for("challenger"),
        _valid_draft("challenger"),
        _qa_with_issue("tone_mismatch_for_preset"),
        _rewrite_patch(
            preset_id="challenger",
            text_by_index={
                1: "We help teams reduce sequence drift and touch base on practical QA controls.",
            },
            preserve_indexes=[0, 2],
        ),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="challenger", sliders=req.sliders.model_dump()))

    assert result.ok is False
    assert result.error
    stage_names = [str(item.get("stage") or "") for item in result.stage_stats]
    assert not any(name.startswith("EMAIL_REWRITE_SALVAGE") for name in stage_names)
    rewrite_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_REWRITE" and item.get("status") == "complete"]
    assert rewrite_entries[-1]["salvage_applied"] is False
    assert rewrite_entries[-1]["salvage_result"] == "not_run"


def test_preset_trace_fields_capture_contract_and_word_counts() -> None:
    req = _request().model_copy(update={"preset_id": "challenger"})
    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms_for("challenger"),
        _valid_draft("challenger"),
        _qa_with_issue("opener_too_soft_for_preset", severity="medium"),
        _rewrite_patch(
            preset_id="challenger",
            text_by_index={
                0: "Hi Alex, Acme's RevOps initiative puts workflow consistency under more scrutiny.",
            },
            preserve_indexes=[1, 2],
        ),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="challenger", sliders=req.sliders.model_dump()))

    assert result.ok is True
    atoms_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "ONE_LINER_COMPRESSOR" and item.get("status") == "complete"]
    generation_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_GENERATION" and item.get("status") == "complete"]
    qa_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_QA" and item.get("status") == "complete"]
    rewrite_entries = [item for item in result.stage_stats if str(item.get("stage") or "") == "EMAIL_REWRITE" and item.get("status") == "complete"]
    assert atoms_entries[-1]["budget_plan_hash"]
    assert atoms_entries[-1]["target_word_budget"] == 61
    assert atoms_entries[-1]["cta_alignment_status"] == "aligned"
    assert generation_entries[-1]["preset_contract_hash"]
    assert generation_entries[-1]["budget_plan_hash"]
    assert generation_entries[-1]["pre_rewrite_word_count"] > 0
    assert generation_entries[-1]["pre_postprocess_word_count"] > 0
    assert qa_entries[-1]["preset_contract_hash"]
    assert qa_entries[-1]["budget_plan_hash"]
    assert qa_entries[-1]["pre_rewrite_word_count"] > 0
    assert rewrite_entries[-1]["post_rewrite_word_count"] > 0


def run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
