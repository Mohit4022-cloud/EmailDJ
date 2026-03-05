from __future__ import annotations

from app.engine.postprocess import deterministic_budget_clamp, deterministic_postprocess_draft, word_count
from app.engine.types import EmailDraft


CTA = "Open to a quick chat to see if this is relevant?"


def test_budget_clamp_trims_to_cap_and_keeps_greeting_and_cta() -> None:
    body = (
        "Hi Alex,\n\n"
        "Acme expanded trademark enforcement coverage and this creates more routing complexity for legal operations. "
        "Teams often struggle with intake consistency when case volume rises quickly. "
        "A clear workflow can reduce delays and keep follow-through predictable. "
        "Structured handoffs also make escalation decisions easier to audit.\n\n"
        f"{CTA}"
    )

    clamped, applied = deterministic_budget_clamp(body=body, max_words=35, cta_line=CTA)

    assert clamped.splitlines()[0].strip() == "Hi Alex,"
    assert clamped.splitlines()[-1].strip() == CTA
    assert clamped.count(CTA) == 1
    assert word_count(clamped) <= 35
    assert "trim_to_max_words" in applied


def test_budget_clamp_removes_duplicate_cta_and_trailing_content() -> None:
    body = (
        "Hi Alex,\n\n"
        "Useful context here.\n\n"
        f"{CTA}\n\n"
        "P.S. this must be removed.\n\n"
        f"{CTA}"
    )

    clamped, applied = deterministic_budget_clamp(body=body, max_words=120, cta_line=CTA)

    assert clamped.splitlines()[-1].strip() == CTA
    assert clamped.count(CTA) == 1
    assert "P.S." not in clamped
    assert "dedupe_cta" in applied
    assert "remove_trailing_after_cta" in applied


def test_budget_clamp_removes_inline_cta_echo_and_keeps_single_final_cta() -> None:
    body = (
        "Hi Alex,\n\n"
        f"Useful context {CTA} should not remain inline.\n\n"
        f"{CTA}"
    )

    clamped, applied = deterministic_budget_clamp(body=body, max_words=120, cta_line=CTA)

    assert clamped.splitlines()[-1].strip() == CTA
    assert clamped.count(CTA) == 1
    assert "remove_inline_cta_echo" in applied


def test_budget_clamp_dedupes_multiple_tail_questions_to_locked_cta_only() -> None:
    body = (
        "Hi Alex,\n\n"
        "Could this improve your RevOps handoff process?\n\n"
        "Would this reduce forecasting variance?\n\n"
        f"{CTA}"
    )

    clamped, applied = deterministic_budget_clamp(body=body, max_words=120, cta_line=CTA)

    assert clamped.splitlines()[-1].strip() == CTA
    assert "Would this reduce forecasting variance?" not in clamped
    assert "dedupe_tail_interrogatives" in applied


def test_budget_clamp_handles_bullets_and_missing_greeting() -> None:
    body = (
        "- Point one explains the workflow shift and expected KPI impact.\n"
        "- Point two explains why consistent routing matters in legal operations.\n"
        "- Point three adds supporting detail for implementation sequencing.\n\n"
        f"{CTA}"
    )

    clamped, _ = deterministic_budget_clamp(body=body, max_words=30, cta_line=CTA)

    assert clamped
    assert clamped.splitlines()[-1].strip() == CTA
    assert word_count(clamped) <= 30


def test_budget_clamp_extremely_small_budget_keeps_greeting_and_cta() -> None:
    body = (
        "Hi Alex,\n\n"
        "This body is intentionally verbose and will exceed tiny budgets quickly with extra filler text.\n\n"
        f"{CTA}"
    )

    clamped, _ = deterministic_budget_clamp(body=body, max_words=3, cta_line=CTA)

    assert clamped.splitlines()[0].strip() == "Hi Alex,"
    assert clamped.splitlines()[-1].strip() == CTA
    assert clamped.strip()


def test_postprocess_trims_subject_to_70_and_keeps_cta_exact() -> None:
    draft = EmailDraft(
        subject="Acme trademark enforcement workflow idea for multi-region legal operations follow-up",
        body=f"Hi Alex,\n\nShort context.\n\n{CTA}",
    )

    result = deterministic_postprocess_draft(draft, max_words=80, cta_line=CTA)

    assert len(result.draft.subject) <= 70
    assert result.draft.body.splitlines()[-1].strip() == CTA
    assert "trim_subject_to_70" in result.applied
