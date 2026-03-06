from __future__ import annotations

import json
from dataclasses import replace
from typing import Any
from uuid import uuid4

from app.config import load_settings
from app.engine.ai_orchestrator import AIOrchestrator
from app.engine.brief_cache import BriefCache
from app.engine.tracer import Trace
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
                "cta_question_suggestion": "quick review",
                "risk_flags": [],
            },
        ],
    }


def _atoms() -> dict[str, Any]:
    return {
        "version": "1",
        "selected_angle_id": "angle_1",
        "used_hook_ids": ["hook_1"],
        "opener_line": "Noticed Acme is prioritizing RevOps workflow consistency.",
        "value_line": "Teams usually improve meeting quality when messaging execution is consistent.",
        "proof_line": "Our workflow QA controls are designed for that consistency.",
        "cta_line": CTA,
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
        "rewrite_plan": ["Keep opener specific and tighten wording."],
    }


def _orchestrator(responses: list[Any]) -> AIOrchestrator:
    settings = replace(load_settings(), app_env="test")
    return AIOrchestrator(openai=StubOpenAI(responses), settings=settings, brief_cache=BriefCache())


def _extract_context_json_from_user_prompt(content: str) -> dict[str, Any]:
    marker = "CONTEXT JSON:\\n"
    start = content.index(marker) + len(marker)
    end = content.rfind("\\n\\nOutput")
    return json.loads(content[start:end])


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
    assert result.error["stage"] == "VALIDATION"


def test_preset_browse_returns_mixed_success_and_error_variants() -> None:
    req = _request().model_copy(update={"mode": "preset_browse", "preset_ids": ["direct", "challenger"]})
    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        _valid_draft("direct"),
        _qa(pass_rewrite_needed=False),
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
    req = _request()
    wrong_cta_draft = _valid_draft()
    wrong_cta_draft["body"] = wrong_cta_draft["body"].replace(CTA, "Can we connect this week?")

    orchestrator = _orchestrator([
        _brief(),
        _fit_map(),
        _angles(),
        _atoms(),
        wrong_cta_draft,
        _qa(pass_rewrite_needed=False),
        _valid_draft(),
    ])

    trace = Trace(str(uuid4()), "test")
    result = run(orchestrator.run_pipeline_single(request=req, trace=trace, preset_id="direct", sliders=req.sliders.model_dump()))

    assert result.ok is True
    assert result.body
    assert result.body.rstrip().endswith(CTA)
    assert result.body.count(CTA) == 1


def test_empty_proof_line_is_normalized_to_proof_gap_before_stage_c() -> None:
    req = _request()
    atoms_without_proof = _atoms()
    atoms_without_proof["proof_line"] = "   "

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
    assert message_atoms["proof_line"] == ""
    assert message_atoms["proof_gap"] is True


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

    stage_starts = [str(item.get("stage") or "") for item in result.stage_stats if item.get("status") == "started"]
    assert stage_starts.count("CONTEXT_SYNTHESIS") == 1
    assert stage_starts.count("FIT_REASONING") == 1
    assert stage_starts.count("ANGLE_PICKER") == 1
    assert stage_starts.count("ONE_LINER_COMPRESSOR") == 1


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
        _qa(pass_rewrite_needed=True),
        rewritten,
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


def run(awaitable):
    import asyncio

    return asyncio.run(awaitable)
