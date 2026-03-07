from __future__ import annotations

from difflib import SequenceMatcher

import pytest

from email_generation.generation_plan import apply_generation_plan, build_generation_plan
from email_generation.remix_engine import (
    _extract_subject_and_body,
    _prospect_owns_offer_lock_violations,
    _repair_prospect_owns_offer_lock,
    build_draft,
    create_session_payload,
)
from email_generation.runtime_policies import rollout_context


def _base_session(title: str, preset_id: str) -> dict:
    with rollout_context(endpoint="generate", bucket_key=f"{title}:{preset_id}"):
        return create_session_payload(
            prospect={
                "name": "Alex Doe",
                "title": title,
                "company": "SignalForge",
                "linkedin_url": "https://linkedin.com/in/alex-doe",
            },
            prospect_first_name="Alex",
            research_text=(
                "SignalForge announced a 2026 outbound quality initiative and opened 12 SDR roles in Q1. "
                "Leadership tied pipeline review to reply quality in the latest earnings call."
            ),
            initial_style={"formality": 0.1, "orientation": 0.2, "length": -0.2, "assertiveness": 0.2},
            offer_lock="Remix Studio",
            cta_offer_lock=None,
            cta_type=None,
            company_context={
                "company_name": "Corsearch",
                "company_url": "https://corsearch.com",
                "current_product": "Remix Studio",
                "other_products": "Search\nEnrich",
                "company_notes": (
                    "Customers use structured guardrails to reduce message drift while preserving rep autonomy."
                ),
            },
            preset_id=preset_id,
            response_contract="legacy_text",
        )


def test_no_prospect_owns_guardrail_detects_and_repairs():
    session = {
        "prospect": {"company": "SignalForge"},
        "offer_lock": "Remix Studio",
    }
    draft = (
        "Subject: SignalForge outbound\n"
        "Body:\n"
        "Hi Alex, SignalForge's Remix Studio is improving pipeline hygiene for your Remix Studio motion.\n\n"
        "Would it be useful if I sent a short risk brief?"
    )

    violations = _prospect_owns_offer_lock_violations(draft, session=session)
    assert violations
    repaired, rewritten, snippets = _repair_prospect_owns_offer_lock(draft, session=session)

    assert rewritten is True
    assert snippets
    assert not _prospect_owns_offer_lock_violations(repaired, session=session)
    assert "SignalForge's Remix Studio" not in repaired
    assert "your Remix Studio" not in repaired


def test_persona_router_exec_vs_standard(monkeypatch):
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT", "100")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_GLOBAL", "0")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT", "0")

    exec_session = _base_session("CEO", "headliner")
    with rollout_context(endpoint="generate", bucket_key="exec"):
        exec_plan = build_generation_plan(
            session=exec_session,
            style_sliders={"tone_formal_casual": 45, "framing_problem_outcome": 70, "length_short_long": 80, "stance_bold_diplomatic": 45},
            preset_id="headliner",
            cta_type=None,
        )
    assert exec_plan.persona_route == "exec"
    assert exec_plan.length_target["max_words"] <= 90
    assert exec_plan.structure_template == ["outcome", "problem", "cta"]

    director_session = _base_session("Director Brand Protection", "headliner")
    with rollout_context(endpoint="generate", bucket_key="director"):
        director_plan = build_generation_plan(
            session=director_session,
            style_sliders={"tone_formal_casual": 45, "framing_problem_outcome": 70, "length_short_long": 80, "stance_bold_diplomatic": 45},
            preset_id="headliner",
            cta_type=None,
        )
    assert director_plan.persona_route == "standard"
    assert director_plan.length_target["max_words"] >= 110


def test_exec_route_applies_even_when_persona_flag_off(monkeypatch):
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_GLOBAL", "0")
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT", "0")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_GLOBAL", "0")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT", "0")

    exec_session = _base_session("CEO", "straight_shooter")
    with rollout_context(endpoint="generate", bucket_key="exec-flag-off"):
        exec_plan = build_generation_plan(
            session=exec_session,
            style_sliders={"tone_formal_casual": 45, "framing_problem_outcome": 70, "length_short_long": 80, "stance_bold_diplomatic": 45},
            preset_id="straight_shooter",
            cta_type=None,
        )
    assert exec_plan.persona_route == "exec"
    assert exec_plan.length_target["max_words"] <= 90
    assert exec_plan.structure_template == ["outcome", "problem", "cta"]


def test_build_generation_plan_sanitizes_named_fact_hint(monkeypatch):
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT", "100")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_GLOBAL", "0")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT", "0")

    session = _base_session("VP Legal", "straight_shooter")
    with rollout_context(endpoint="generate", bucket_key="sanitize-fact-hint"):
        plan = build_generation_plan(
            session=session,
            style_sliders={"tone_formal_casual": 45, "framing_problem_outcome": 50, "length_short_long": 50, "stance_bold_diplomatic": 45},
            preset_id="straight_shooter",
            cta_type=None,
        )

    assert "Marcus Williams" not in plan.wedge_problem
    assert "Acme Consumer Brands" not in plan.wedge_problem


def test_sanitize_fact_hint_redacts_non_prospect_full_names():
    from email_generation.generation_plan import _sanitize_fact_hint

    hint = _sanitize_fact_hint(
        "Kevin leads brand trust and protection at Cascade Dynamics, reporting to Robert Kline.",
        prospect_name="Kevin Tan",
        company="Cascade Dynamics",
        first_name="Kevin",
    )

    assert "Robert Kline" not in hint
    assert "leadership" in hint
    assert "your team" in hint


def test_apply_generation_plan_softens_offer_lock_casing_in_body(monkeypatch):
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT", "100")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_GLOBAL", "0")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT", "0")

    session = _base_session("VP Legal", "straight_shooter")
    style_sliders = {
        "tone_formal_casual": 45,
        "framing_problem_outcome": 50,
        "length_short_long": 50,
        "stance_bold_diplomatic": 45,
    }
    with rollout_context(endpoint="generate", bucket_key="soften-offer-lock"):
        plan = build_generation_plan(
            session=session,
            style_sliders=style_sliders,
            preset_id="straight_shooter",
            cta_type=None,
        )
    _, body = apply_generation_plan(
        subject="Test subject",
        body="Hi Alex, Trademark Search, Screening, and Brand Protection helps teams keep quality high.",
        session=session,
        style_sliders=style_sliders,
        plan=plan,
    )
    narrative = body.split("\n\n", 1)[0]
    offer_lock = session["offer_lock"]
    normalized = offer_lock[0].upper() + offer_lock[1:].lower()
    assert offer_lock not in narrative
    assert normalized in narrative


@pytest.mark.asyncio
async def test_preset_true_rewrite_generates_semantically_distinct_outputs(monkeypatch):
    monkeypatch.setenv("REDIS_FORCE_INMEMORY", "1")
    monkeypatch.setenv("USE_PROVIDER_STUB", "1")
    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "warn")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_PRESET_TRUE_REWRITE_ROLLOUT_PERCENT", "100")
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_GLOBAL", "1")
    monkeypatch.setenv("FEATURE_PERSONA_ROUTER_ROLLOUT_PERCENT", "100")

    style_profile = {"formality": 0.1, "orientation": 0.2, "length": -0.2, "assertiveness": 0.2}
    headliner_session = _base_session("Director Brand Protection", "headliner")
    giver_session = _base_session("Director Brand Protection", "giver")

    with rollout_context(endpoint="generate", bucket_key="headliner-case"):
        headliner_result = await build_draft(session=headliner_session, style_profile=style_profile)
    with rollout_context(endpoint="generate", bucket_key="giver-case"):
        giver_result = await build_draft(session=giver_session, style_profile=style_profile)

    _, headliner_body = _extract_subject_and_body(headliner_result.draft)
    _, giver_body = _extract_subject_and_body(giver_result.draft)
    similarity = SequenceMatcher(None, headliner_body, giver_body).ratio()
    assert similarity < 0.85
