from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))


def _session_payload():
    from email_generation.remix_engine import create_session_payload

    return create_session_payload(
        prospect={
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex-doe",
        },
        research_text=(
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


def test_validate_ctco_output_allows_non_ask_mentions_of_pilot():
    from email_generation.remix_engine import style_profile_to_ctco_sliders, validate_ctco_output

    session = _session_payload()
    sliders = style_profile_to_ctco_sliders({"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0})
    draft = (
        "Subject: Remix Studio for Acme's outbound outcomes\n"
        "Body:\n"
        "Hi Alex, Acme recently launched outbound AI initiatives and proposed a low-friction pilot to improve reply quality in enterprise accounts. "
        "Remix Studio helps your SDR team keep messaging relevant while preserving control over tone and accuracy.\n\n"
        "Open to a quick chat to see if this is relevant?"
    )

    violations = validate_ctco_output(draft=draft, session=session, style_sliders=sliders)
    assert "additional_cta_detected" not in violations


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


@pytest.mark.asyncio
async def test_build_draft_retries_after_validation_failure_then_succeeds(monkeypatch):
    import email_generation.remix_engine as remix_engine

    session = _session_payload()
    calls = {"count": 0}

    async def fake_real_generate(prompt, throttled=False):  # noqa: ARG001
        calls["count"] += 1
        if calls["count"] == 1:
            return (
                "Subject: quick note\n"
                "Body:\n"
                "Hi Alex, this is relevant to Acme.\n\n"
                "Open to a 15-minute walkthrough next week?"
            )
        return (
            "Subject: Remix Studio for Acme's outbound outcomes\n"
            "Body:\n"
            "Hi Alex, Acme can improve qualified replies by making outbound messaging more specific to active priorities. "
            "Acme recently launched outbound AI initiatives and is pushing for higher quality replies in enterprise accounts. "
            "Remix Studio helps reps produce context-specific messaging with consistent quality controls. "
            "This supports your SDR Manager goals without adding process drag.\n\n"
            "Open to a quick chat to see if this is relevant?"
        )

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

    async def always_invalid(prompt, throttled=False):  # noqa: ARG001
        return (
            "Subject: quick note\n"
            "Body:\n"
            "Hi Alex, this should be relevant.\n\n"
            "Open to a 15-minute walkthrough next week?"
        )

    monkeypatch.setattr(remix_engine, "_mode", lambda: "real")
    monkeypatch.setattr(remix_engine, "_real_generate", always_invalid)

    with pytest.raises(ValueError, match="ctco_validation_failed"):
        await remix_engine.build_draft(
            session=session,
            style_profile={"formality": 0.0, "orientation": 0.0, "length": -0.8, "assertiveness": 0.0},
        )
