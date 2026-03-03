import os
from pathlib import Path
import re
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("REDIS_FORCE_INMEMORY", "1")


def _session_payload(research_text: str | None = None):
    from email_generation.remix_engine import create_session_payload

    return create_session_payload(
        prospect={
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        research_text=research_text
        or (
            "Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
            "The SDR org is under pressure to improve response rates while keeping execution efficient."
        ),
        initial_style={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
        offer_lock="Remix Studio",
        cta_offer_lock="Open to a quick chat to see if this is relevant?",
        cta_type="question",
        company_context={
            "company_name": "EmailDJ",
            "company_url": "https://emaildj.ai",
            "current_product": "Remix Studio",
            "other_products": "Prospect Enrichment, Sequence QA",
            "company_notes": "We help teams improve reply quality with controlled personalization.",
        },
    )


def _extract_body_text(draft: str) -> str:
    marker = "\nBody:\n"
    if marker not in draft:
        return ""
    return draft.split(marker, 1)[1].strip()


def test_validate_ctco_output_flags_internal_leakage():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Remix Studio helps Acme improve SDR quality.\n"
        "We use OpenAI prompts for this.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert any(v.startswith("internal_leakage_term:") for v in violations)


def test_parse_structured_output_reports_salvage_method_for_wrapped_text():
    from email_generation.remix_engine import _parse_structured_output

    raw = 'prefix text {"subject":"Hello","body":"Hi Alex, body copy."} trailing text'
    subject, body, parse_method = _parse_structured_output(raw)
    assert subject == "Hello"
    assert "Hi Alex" in body
    assert parse_method == "salvage_substring"


def test_parse_structured_output_rejects_wrapped_text_without_salvage():
    from email_generation.remix_engine import _parse_structured_output

    raw = 'prefix text {"subject":"Hello","body":"Hi Alex, body copy."} trailing text'
    with pytest.raises(ValueError, match="non_json_output"):
        _parse_structured_output(raw, allow_salvage=False)


def test_create_session_payload_extracts_allowed_facts_and_strips_instructions():
    from email_generation.remix_engine import create_session_payload

    session = create_session_payload(
        prospect={
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        research_text=(
            "Acme launched a new enterprise outbound initiative in January 2026. "
            "Outreach should propose a pilot that shows measurable results. "
            "The SDR team is hiring 12 reps this quarter."
        ),
        initial_style={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
        offer_lock="Remix Studio",
        cta_offer_lock="Open to a quick chat to see if this is relevant?",
        cta_type="question",
    )

    assert session["allowed_facts"]
    assert any("launched" in fact.lower() for fact in session["allowed_facts"])
    assert "outreach should" not in session["research_text_sanitized"].lower()
    assert "propose a pilot" not in session["research_text_sanitized"].lower()


def test_create_session_payload_derives_first_name_from_honorific():
    from email_generation.remix_engine import create_session_payload

    session = create_session_payload(
        prospect={
            "name": "Dr. Maya Chen",
            "title": "Revenue Operations Lead",
            "company": "Bluebird Systems",
            "linkedin_url": "https://linkedin.com/in/maya-chen",
        },
        research_text="Bluebird Systems launched a QA initiative for outbound consistency this quarter.",
        initial_style={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
        offer_lock="Compliance QA",
        cta_offer_lock="Open to a 10-min call next week?",
        cta_type="question",
    )

    assert session["prospect_first_name"] == "Maya"


def test_validate_ctco_output_flags_near_match_cta():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme's outbound outcomes\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Remix Studio helps your SDR team keep messaging relevant while preserving control over tone and accuracy.\n\n"
        "Open to a quick call to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "cta_near_match_detected" in violations


def test_validate_ctco_output_flags_signoff_before_cta():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": 0.6, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Remix Studio helps your SDR team keep messaging relevant while preserving control over tone and accuracy for managers. "
        "This gives the team a cleaner way to scale quality across higher-volume outreach without adding extra workflow drag. "
        "Best regards, Alex.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert any(v.startswith("signoff_before_cta") for v in violations)


def test_validate_ctco_output_flags_offer_lock_missing_in_body():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Your SDR team is balancing personalization quality with workflow consistency this quarter.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "offer_lock_body_verbatim_missing" in violations


def test_validate_ctco_output_blocks_banned_phrases():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Remix Studio helps teams improve pipeline outcomes without adding process overhead.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "banned_phrase:pipeline outcomes" in violations


def test_validate_ctco_output_forbidden_product_uses_word_boundaries():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    session["company_context"]["other_products"] = "Search, Sequence QA"
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and your SDR team is refining research workflows. "
        "Remix Studio helps keep messaging controlled without adding process overhead.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "forbidden_other_product_mentioned:Search" not in violations


@pytest.mark.asyncio
async def test_build_draft_long_mode_does_not_inject_forbidden_search_enrich(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload(
        research_text=(
            "Acme is tightening outbound quality controls and improving enterprise reply handling. "
            "The SDR org is prioritizing credible messaging this quarter."
        )
    )
    session["company_context"]["other_products"] = "Search, Enrich"
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    style_profile = {"formality": 0.0, "orientation": 0.0, "length": 1.0, "assertiveness": 0.0}
    result = await remix_engine.build_draft(session=session, style_profile=style_profile)
    sliders = remix_engine.style_profile_to_ctco_sliders(style_profile)
    violations = remix_engine.validate_ctco_output(result.draft, session=session, style_sliders=sliders)

    assert "forbidden_other_product_mentioned:Search" not in violations
    assert "forbidden_other_product_mentioned:Enrich" not in violations


@pytest.mark.asyncio
async def test_build_draft_rewrites_forbidden_model_signal_in_real_mode(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine
    from email_generation.quick_generate import GenerateResult

    session = _session_payload(
        research_text=(
            "Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
            "The SDR org is under pressure to improve response rates while keeping execution efficient."
        )
    )
    session["company_context"]["other_products"] = "Search, Enrich"
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")

    async def contaminated_output(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        text = json.dumps(
            {
                "subject": "Remix Studio for Acme",
                "body": (
                    "Hi Alex, Search and Enrich workflows are top of mind for your team this quarter. "
                    "Remix Studio helps keep outbound messaging controlled without adding process overhead.\n\n"
                    "Open to a quick chat to see if this is relevant?"
                ),
            }
        )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=1)

    monkeypatch.setattr(remix_engine, "_real_generate", contaminated_output)
    style_profile = {"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0}
    sliders = remix_engine.style_profile_to_ctco_sliders(style_profile)

    result = await remix_engine.build_draft(session=session, style_profile=style_profile)
    violations = remix_engine.validate_ctco_output(result.draft, session=session, style_sliders=sliders)

    assert "forbidden_other_product_mentioned:Search" not in violations
    assert "forbidden_other_product_mentioned:Enrich" not in violations
    assert re.search(r"\bsearch\b", result.draft.lower()) is None
    assert re.search(r"\benrich\b", result.draft.lower()) is None


@pytest.mark.asyncio
async def test_build_draft_real_prompt_does_not_include_other_products_mapping(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine
    from email_generation.quick_generate import GenerateResult

    session = _session_payload()
    session["company_context"]["other_products"] = "Search, Enrich"
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    captured_prompt: dict[str, object] = {}

    async def capture_prompt(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        captured_prompt["value"] = prompt
        text = json.dumps(
            {
                "subject": "Remix Studio for Acme",
                "body": (
                    "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
                    "Remix Studio helps keep outbound messaging controlled without adding process overhead.\n\n"
                    "Open to a quick chat to see if this is relevant?"
                ),
            }
        )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=1)

    monkeypatch.setattr(remix_engine, "_real_generate", capture_prompt)
    await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.3, "assertiveness": 0.0},
    )

    prompt_text = json.dumps(captured_prompt.get("value", ""))
    assert "other_products_services_mapping" not in prompt_text
    assert "Search, Enrich" not in prompt_text


def test_validate_ctco_output_flags_non_first_name_greeting():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme's outbound outcomes\n"
        "Body:\n"
        "Hi Alex Doe, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Remix Studio helps your SDR team keep messaging relevant while preserving control over tone and accuracy.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "greeting_first_name_mismatch" in violations
    assert "greeting_not_first_name_only" in violations


def test_validate_ctco_output_flags_unsubstantiated_statistical_claim():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Remix Studio delivered 25% improvement in response quality for similar teams while preserving control.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "unsubstantiated_statistical_claim" in violations


def test_validate_ctco_output_blocks_statistical_claim_even_if_only_research_supports_it():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload(
        research_text=(
            "Acme recently launched outbound AI initiatives and reported a 25% improvement in response quality across enterprise accounts. "
            "The SDR team is under pressure to keep execution efficient."
        )
    )
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
        "Remix Studio supports your SDR team with controlled personalization and sustained 25% improvement in response quality.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "unsubstantiated_statistical_claim" in violations


def test_validate_ctco_output_blocks_generic_ai_opener_without_research_anchoring():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload(
        research_text=(
            "Palantir is modernizing outbound enforcement workflows while improving coverage consistency. "
            "The team is focused on practical delivery in Q2."
        )
    )
    session["generation_plan"]["hook_strategy"] = "domain_hook"
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, As Palantir scales its enterprise AI initiatives, your team is likely balancing output quality and speed. "
        "Remix Studio helps keep outbound controls specific and enforceable.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "banned_generic_ai_opener" in violations


def test_validate_ctco_output_allows_generic_ai_opener_with_research_anchored_strategy():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload(
        research_text=(
            "As Palantir scales its enterprise AI initiatives, the team is tightening enforcement workflows and operator throughput. "
            "The SDR org is prioritizing credible outreach execution."
        )
    )
    session["generation_plan"]["hook_strategy"] = "research_anchored"
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme\n"
        "Body:\n"
        "Hi Alex, As Palantir scales its enterprise AI initiatives, your team is likely balancing output quality and speed. "
        "Remix Studio helps keep outbound controls specific and enforceable.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "banned_generic_ai_opener" not in violations


@pytest.mark.asyncio
async def test_build_draft_retries_after_validation_failure_then_succeeds(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    calls = {"count": 0}

    from email_generation.quick_generate import GenerateResult

    async def fake_real_generate(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] == 1:
            text = "Subject: invalid\nBody: invalid"
        else:
            text = json.dumps(
                {
                    "subject": "Remix Studio for Acme",
                    "body": (
                        "Hi Alex, Acme recently launched outbound AI initiatives in enterprise accounts and your SDR team "
                        "is under pressure to improve response quality without adding process overhead. "
                        "Remix Studio helps keep messaging specific and controlled while fitting your existing workflow.\n\n"
                        "Open to a quick chat to see if this is relevant?"
                    ),
                }
            )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=calls["count"])

    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", fake_real_generate)

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0},
    )

    assert calls["count"] == 2
    assert "Open to a quick chat to see if this is relevant?" in result.draft
    assert "Subject:" in result.draft
    assert "Body:" in result.draft


@pytest.mark.asyncio
async def test_build_draft_structured_output_retries_before_salvage(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine
    from email_generation.quick_generate import GenerateResult

    session = _session_payload()
    calls = {"count": 0}
    valid_body = (
        "Hi Alex, Acme recently launched outbound AI initiatives in enterprise accounts and your SDR team is balancing "
        "response quality with execution speed across weekly outbound volume. Remix Studio helps keep messaging specific "
        "and controlled while preserving manager visibility into standards and consistency across reps.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    async def wrapped_then_strict(prompt, task="quick_generate", throttled=False, output_token_budget=None):  # noqa: ARG001
        calls["count"] += 1
        payload = json.dumps({"subject": "Remix Studio for Acme", "body": valid_body})
        if calls["count"] == 1:
            payload = f"prefix {payload} suffix"
        return GenerateResult(
            text=payload,
            provider="openai",
            model_name="gpt-4.1-nano",
            cascade_reason="primary",
            attempt_count=calls["count"],
            finish_reason="stop",
        )

    monkeypatch.setenv("FEATURE_STRUCTURED_OUTPUT", "1")
    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "1")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", wrapped_then_strict)

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0},
    )

    assert calls["count"] == 2
    assert result.json_repair_count == 1
    assert "Subject:" in result.draft
    assert "Body:" in result.draft


@pytest.mark.asyncio
async def test_build_draft_fallback_salvage_only_after_two_parse_retries(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine
    from email_generation.quick_generate import GenerateResult

    session = _session_payload()
    calls = {"count": 0}
    valid_body = (
        "Hi Alex, Acme recently launched outbound AI initiatives in enterprise accounts and your SDR team is balancing "
        "response quality with execution speed across weekly outbound volume. Remix Studio helps keep messaging specific "
        "and controlled while preserving manager visibility into standards and consistency across reps.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    async def wrapped_fallback(prompt, task="quick_generate", throttled=False, output_token_budget=None):  # noqa: ARG001
        calls["count"] += 1
        payload = json.dumps({"subject": "Remix Studio for Acme", "body": valid_body})
        return GenerateResult(
            text=f"prefix {payload} suffix",
            provider="anthropic",
            model_name="claude-3-5-haiku-latest",
            cascade_reason="fallback_after_openai_error",
            attempt_count=calls["count"],
            finish_reason="stop",
        )

    monkeypatch.setenv("FEATURE_STRUCTURED_OUTPUT", "1")
    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "1")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", wrapped_fallback)

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0},
    )

    assert calls["count"] == 3
    assert result.json_repair_count == 2
    assert "Subject:" in result.draft
    assert "Body:" in result.draft


@pytest.mark.asyncio
async def test_build_draft_fluency_repair_retries_on_unmatched_parentheses(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine
    from email_generation.quick_generate import GenerateResult

    session = _session_payload()
    calls = {"count": 0}
    broken_body = (
        "Hi Alex, Acme recently launched outbound AI initiatives in enterprise accounts and your SDR team is balancing "
        "response quality with execution speed across weekly outbound volume. Remix Studio helps keep messaging specific "
        "and controlled while preserving manager visibility (into standards and consistency across reps.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )
    fixed_body = broken_body.replace("(into", "into")

    async def fluency_retry(prompt, task="quick_generate", throttled=False, output_token_budget=None):  # noqa: ARG001
        calls["count"] += 1
        body = broken_body if calls["count"] == 1 else fixed_body
        return GenerateResult(
            text=json.dumps({"subject": "Remix Studio for Acme", "body": body}),
            provider="openai",
            model_name="gpt-4.1-nano",
            cascade_reason="primary",
            attempt_count=calls["count"],
            finish_reason="stop",
        )

    monkeypatch.setenv("FEATURE_FLUENCY_REPAIR", "1")
    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "1")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", fluency_retry)
    monkeypatch.setattr(
        remix_engine,
        "apply_generation_plan",
        lambda subject, body, session, style_sliders, plan: (subject, body),
    )

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0},
    )

    assert calls["count"] == 1
    assert result.violation_retry_count >= 1
    assert "Subject:" in result.draft
    assert "Body:" in result.draft


@pytest.mark.asyncio
async def test_build_draft_deterministic_repair_fixes_cta_forbidden_and_length(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    session["company_context"]["other_products"] = "Search, Sequence QA"
    calls = {"count": 0}

    from email_generation.quick_generate import GenerateResult

    async def noisy_real_output(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        calls["count"] += 1
        text = json.dumps(
            {
                "subject": "Search angle for Acme",
                "body": (
                    "Hi Alex, Acme recently launched outbound AI initiatives and the SDR org is balancing quality with speed. "
                    "Remix Studio helps keep outbound messaging controlled.\n\n"
                    "Open to a quick call to see if this is relevant?\n"
                    "Open to a quick chat to see if this is relevant?"
                ),
            }
        )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=calls["count"])

    style_profile = {"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0}
    style_sliders = remix_engine.style_profile_to_ctco_sliders(style_profile)

    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "1")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", noisy_real_output)

    result = await remix_engine.build_draft(
        session=session,
        style_profile=style_profile,
    )

    violations = remix_engine.validate_ctco_output(result.draft, session=session, style_sliders=style_sliders)
    assert violations == []
    assert calls["count"] == 1
    assert result.violation_retry_count == 0
    assert result.repaired is False


@pytest.mark.asyncio
async def test_build_draft_fails_after_retry_exhaustion(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    calls = {"count": 0}

    from email_generation.quick_generate import GenerateResult

    async def always_invalid(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        calls["count"] += 1
        return GenerateResult(text="not valid json", provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=calls["count"])

    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", always_invalid)

    with pytest.raises(ValueError, match="invalid_json_output"):
        await remix_engine.build_draft(
            session=session,
            style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0},
        )
    assert calls["count"] == remix_engine.MAX_VALIDATION_ATTEMPTS


@pytest.mark.asyncio
async def test_build_draft_warn_mode_returns_with_claim_violation(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine

    session = _session_payload()

    from email_generation.quick_generate import GenerateResult

    async def claim_heavy_output(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        text = json.dumps(
            {
                "subject": "Remix Studio for Acme",
                "body": (
                    "Hi Alex, Acme recently launched outbound AI initiatives and the SDR team is balancing scale with message quality. "
                    "Remix Studio helps keep messaging controlled, and teams often report a 25% improvement in response quality after rollout. "
                    "This keeps output aligned with your process while maintaining execution speed in enterprise sequences.\n\n"
                    "Open to a quick chat to see if this is relevant?"
                ),
            }
        )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=1)

    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "warn")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "0")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", claim_heavy_output)

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.3, "assertiveness": 0.0},
    )

    assert "Subject:" in result.draft
    assert result.enforcement_level == "warn"
    assert result.repair_loop_enabled is False
    assert "unsubstantiated_statistical_claim" not in result.violation_codes
    assert result.violation_count == 0


@pytest.mark.asyncio
async def test_build_draft_block_mode_fails_without_repair_retry(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    calls = {"count": 0}

    from email_generation.quick_generate import GenerateResult

    async def claim_heavy_output(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        calls["count"] += 1
        text = json.dumps(
            {
                "subject": "Remix Studio for Acme",
                "body": (
                    "Hi Alex, Acme recently launched outbound AI initiatives and the SDR team is balancing scale with message quality. "
                    "Remix Studio is proven to deliver measurable lift in reply quality without adding process overhead.\n\n"
                    "Open to a quick chat to see if this is relevant?"
                ),
            }
        )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=calls["count"])

    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "block")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "1")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", claim_heavy_output)

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.3, "assertiveness": 0.0},
    )
    assert calls["count"] == 1
    assert "proven" not in result.draft.lower()


@pytest.mark.asyncio
async def test_build_draft_enforces_first_name_greeting_in_mock_mode(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.2, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    )
    body = _extract_body_text(result.draft)
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    assert first_line.startswith("Hi Alex,") or first_line.startswith("Hello Alex,")


@pytest.mark.asyncio
async def test_build_draft_slider_length_bands_are_deterministic(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    short = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": -1.0, "assertiveness": 0.0},
    )
    long = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 1.0, "assertiveness": 0.0},
    )
    short_words = len(re.findall(r"[A-Za-z0-9']+", _extract_body_text(short.draft)))
    long_words = len(re.findall(r"[A-Za-z0-9']+", _extract_body_text(long.draft)))

    assert 55 <= short_words <= 75
    assert 110 <= long_words <= 160
    assert long_words > short_words


@pytest.mark.asyncio
async def test_build_draft_long_mode_has_no_repeated_sentences(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload(
        research_text=(
            "Acme is scaling counterfeit enforcement and needs faster first-week action handoffs. "
            "The team is balancing quality, trust, and throughput."
        )
    )
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 1.0, "assertiveness": 0.0},
    )
    body = _extract_body_text(result.draft)
    content = "\n".join(body.splitlines()[:-1]).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", content) if s.strip()]
    normalized = [re.sub(r"[^a-z0-9 ]", "", s.lower()).strip() for s in sentences]
    counts = {key: normalized.count(key) for key in set(normalized)}

    assert counts
    assert max(counts.values()) <= 1
    assert body.lower().count("this keeps messaging relevant, credible, and easy for your team to action.") <= 1


@pytest.mark.asyncio
async def test_build_draft_formality_and_assertiveness_sliders_change_output(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    session["cta_offer_lock"] = ""
    session["cta_type"] = "question"
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    formal = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": -1.0, "orientation": 0.0, "length": 0.0, "assertiveness": -1.0},
    )
    casual = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 1.0, "orientation": 0.0, "length": 0.0, "assertiveness": 1.0},
    )

    formal_first_line = next((line.strip() for line in _extract_body_text(formal.draft).splitlines() if line.strip()), "")
    casual_first_line = next((line.strip() for line in _extract_body_text(casual.draft).splitlines() if line.strip()), "")
    formal_cta = _extract_body_text(formal.draft).splitlines()[-1].strip()
    casual_cta = _extract_body_text(casual.draft).splitlines()[-1].strip()

    assert formal_first_line.startswith("Hello Alex,")
    assert casual_first_line.startswith("Hi Alex,")
    assert formal_cta.startswith("Open to ")
    assert casual_cta.startswith("If useful, open to ")


@pytest.mark.asyncio
async def test_build_draft_cta_lock_overrides_cta_type(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    session["cta_offer_lock"] = "Open to a 17-min call for a first-week counterfeit sweep + teardown? Worth a look / Not a priority?"
    session["cta_type"] = "event_invite"
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    )
    assert _extract_body_text(result.draft).splitlines()[-1].strip() == session["cta_offer_lock"]


@pytest.mark.asyncio
async def test_build_draft_uses_cta_type_when_lock_is_blank(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    session["cta_offer_lock"] = ""
    session["cta_type"] = "event_invite"
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    )
    cta_line = _extract_body_text(result.draft).splitlines()[-1].strip()
    assert "Open to a" in cta_line
    assert "Worth a look / Not a priority?" in cta_line
    assert "quick chat to see if this is relevant" not in cta_line


@pytest.mark.asyncio
async def test_build_draft_problem_vs_outcome_slider_changes_opener(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    problem_led = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": -1.0, "length": 0.0, "assertiveness": 0.0},
    )
    outcome_led = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 1.0, "length": 0.0, "assertiveness": 0.0},
    )

    problem_body = _extract_body_text(problem_led.draft).lower()
    outcome_body = _extract_body_text(outcome_led.draft).lower()
    assert "remix studio helps" in outcome_body
    assert problem_body != outcome_body


@pytest.mark.asyncio
async def test_build_draft_preset_strategy_changes_structure_and_cta(monkeypatch):
    import email_generation.remix_engine as remix_engine

    monkeypatch.setattr(remix_engine, "_mode", lambda: "mock")

    straight_session = _session_payload()
    straight_session["preset_id"] = "straight_shooter"
    straight_session["cta_offer_lock"] = ""
    straight_session["cta_type"] = None
    straight = await remix_engine.build_draft(
        session=straight_session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    )

    giver_session = _session_payload()
    giver_session["preset_id"] = "giver"
    giver_session["cta_offer_lock"] = ""
    giver_session["cta_type"] = None
    giver = await remix_engine.build_draft(
        session=giver_session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    )

    assert straight_session["generation_plan"]["hook_type"] != giver_session["generation_plan"]["hook_type"]
    assert "Open to a" in straight.draft
    assert "send 3 examples" in giver.draft


@pytest.mark.asyncio
async def test_build_draft_rewrites_unverified_numeric_claims(monkeypatch):
    import json

    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    session["cta_offer_lock"] = ""
    session["cta_type"] = None
    monkeypatch.setenv("EMAILDJ_STRICT_LOCK_ENFORCEMENT_LEVEL", "repair")
    monkeypatch.setenv("EMAILDJ_REPAIR_LOOP_ENABLED", "1")
    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")

    from email_generation.quick_generate import GenerateResult

    async def fake_real_generate(prompt, task="quick_generate", throttled=False):  # noqa: ARG001
        text = json.dumps(
            {
                "subject": "Remix Studio for Acme",
                "body": (
                    "Hi Alex, Acme recently launched outbound AI initiatives and your team is balancing quality with speed. "
                    "Remix Studio guarantees 99.9% accuracy rate and coverage across 400 marketplaces.\n\n"
                    "Open to a quick chat to see if this is relevant?"
                ),
            }
        )
        return GenerateResult(text=text, provider="openai", model_name="gpt-4.1-nano", cascade_reason="primary", attempt_count=1)

    monkeypatch.setattr(remix_engine, "_real_generate", fake_real_generate)
    result = await remix_engine.build_draft(
        session=session,
        style_profile={"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    )
    draft_lower = result.draft.lower()
    assert "99.9%" not in draft_lower
    assert "accuracy rate" not in draft_lower
    assert "400 marketplaces" not in draft_lower
    assert "worth a look / not a priority?" in draft_lower
