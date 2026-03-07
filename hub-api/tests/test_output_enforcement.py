import re

from email_generation.output_enforcement import (
    compose_body_without_padding_loops,
    enforce_cta_last_line,
    long_mode_section_pool,
    sanitize_generic_ai_opener,
)


def test_sanitize_generic_ai_opener_replaces_banned_pattern_without_research_anchor():
    text = (
        "As Acme scales its enterprise AI initiatives, their team is balancing quality and speed. "
        "Remix Studio helps prioritize workflow quality."
    )
    sanitized = sanitize_generic_ai_opener(
        text,
        research_text="Acme is improving workflow automation and outbound triage.",
        hook_strategy="domain_hook",
        company="Acme",
        risk_surface="outbound workflows",
    )

    assert "scales its enterprise ai initiatives" not in sanitized.lower()


def test_sanitize_generic_ai_opener_allows_pattern_when_research_anchored():
    text = (
        "As Acme scales its enterprise AI initiatives, their team is balancing quality and speed. "
        "Remix Studio helps prioritize workflow quality."
    )
    sanitized = sanitize_generic_ai_opener(
        text,
        research_text="As Acme scales its enterprise AI initiatives, the company is tightening controls.",
        hook_strategy="research_anchored",
        company="Acme",
        risk_surface="outbound workflows",
    )

    assert "scales its enterprise ai initiatives" in sanitized.lower()


def test_long_mode_section_pool_avoids_search_enrich_act_copy():
    sections = long_mode_section_pool(
        company_notes="We help with outreach quality controls.",
        allowed_facts=["The team is modernizing enforcement workflows."],
        offer_lock="Brand Protection",
        company="Acme",
    )

    joined = " ".join(sections).lower()
    assert "search, enrich, act" not in joined
    assert "detect risky patterns" in joined


def test_long_mode_section_pool_strips_forbidden_single_word_terms():
    sections = long_mode_section_pool(
        company_notes="Counterfeit queues are climbing this quarter.",
        allowed_facts=["The team wants faster triage."],
        offer_lock="Brand Protection",
        company="Acme",
        forbidden_terms=["Search", "Enrich"],
    )

    joined = " ".join(sections).lower()
    assert "search" not in joined
    assert "enrich" not in joined


def test_long_mode_section_pool_strips_forbidden_multiword_terms():
    sections = long_mode_section_pool(
        company_notes="Prospect Enrichment rollout was paused.",
        allowed_facts=["Sequence QA is being reviewed."],
        offer_lock="Brand Protection",
        company="Acme",
        forbidden_terms=["Prospect Enrichment", "Sequence QA"],
    )

    joined = " ".join(sections).lower()
    assert "prospect enrichment" not in joined
    assert "sequence qa" not in joined


def test_long_mode_section_pool_sanitizes_trusted_by_proof_dump_patterns():
    sections = long_mode_section_pool(
        company_notes=(
            "EmailDJ is the leading platform for outbound email quality control. "
            "Trusted by over 5,000 revenue teams across SaaS, fintech, and enterprise."
        ),
        allowed_facts=[],
        offer_lock="Remix Studio",
        company="Acme",
    )

    joined = " ".join(sections).lower()
    assert "trusted by" not in joined
    assert "two proof points from your notes" not in joined


def test_long_mode_section_pool_keeps_proof_on_seller_notes_not_prospect_facts():
    sections = long_mode_section_pool(
        company_notes="Managers get a clearer review path and tighter escalation workflow.",
        allowed_facts=["Acme launched a new enforcement initiative this quarter."],
        offer_lock="Remix Studio",
        company="Acme",
    )

    assert sections[0].lower().startswith("managers get a clearer review path")
    assert "launched a new enforcement initiative" not in " ".join(sections).lower()


def test_enforce_cta_last_line_removes_signoff_and_duplicate_ctas():
    cta = "Open to a 15-min chat to sanity-check fit? Worth a look / Not a priority?"
    body = (
        "Hi Alex,\n"
        "Acme is tightening outbound quality controls this quarter.\n"
        "Best regards,\n"
        "Open to a quick call next week?\n"
        "Open to a 15-min chat to sanity-check fit? Worth a look / Not a priority?"
    )

    normalized = enforce_cta_last_line(body, cta_line=cta)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]

    assert lines[-1] == cta
    assert sum(1 for line in lines if line == cta) == 1
    assert all("best regards" not in line.lower() for line in lines)
    assert all("quick call next week" not in line.lower() for line in lines)


def test_compose_body_without_padding_loops_preserves_min_after_ngram_cap():
    body = compose_body_without_padding_loops(
        base_sentences=[
            (
                "Hi Jordan, Remix Studio helps revenue teams keep outreach specific "
                "while raising quality from first touch."
            ),
            "EmailDJ is a leading provider of outbound email quality tooling.",
        ],
        extra_sections=[
            "The goal is keeping outreach consistent without adding manager overhead.",
            "Teams usually start with one sequence, verify reply quality, then expand.",
            "That creates a cleaner handoff between rep activity, quality checks, and follow-up actions per account.",
        ],
        cta_line="Open to a quick 15-minute chat next week?",
        min_words=75,
        max_words=110,
    )

    words = len(re.findall(r"[A-Za-z0-9']+", body))
    assert 75 <= words <= 110


def test_compose_body_without_padding_loops_preserves_opener_and_cta_while_inserting_middle():
    cta = "Open to a quick 15-minute chat next week?"
    body = compose_body_without_padding_loops(
        base_sentences=[
            "Hi Jordan, Remix Studio helps revenue teams keep outreach specific while raising quality from first touch.",
            "Managers still need a clean way to review risky messaging before it ships.",
        ],
        extra_sections=[
            "Customers use structured guardrails to reduce message drift while preserving rep autonomy.",
            "In week one, we'd run a focused sweep and teardown, then hand over a prioritized enforcement workflow by risk tier.",
        ],
        cta_line=cta,
        min_words=75,
        max_words=110,
    )

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    narrative = " ".join(lines[:-1])

    assert narrative.startswith("Hi Jordan, Remix Studio helps revenue teams keep outreach specific")
    assert "structured guardrails" in narrative.lower()
    assert lines[-1] == cta
