import os
from pathlib import Path
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


def test_validate_ctco_output_allows_statistical_claim_when_research_supports_it():
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
    assert "unsubstantiated_statistical_claim" not in violations


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
    assert "unsubstantiated_statistical_claim" in result.violation_codes
    assert result.violation_count >= 1


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

    with pytest.raises(ValueError, match="ctco_validation_failed"):
        await remix_engine.build_draft(
            session=session,
            style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.3, "assertiveness": 0.0},
        )
    assert calls["count"] == 1
