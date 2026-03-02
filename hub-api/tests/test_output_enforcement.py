from email_generation.output_enforcement import long_mode_section_pool, sanitize_generic_ai_opener


def test_sanitize_generic_ai_opener_replaces_banned_pattern_without_research_anchor():
    text = (
        "As Palantir scales its enterprise AI initiatives, their team is balancing quality and speed. "
        "Zeal 2.0 helps prioritize enforcement work."
    )
    sanitized = sanitize_generic_ai_opener(
        text,
        research_text="Palantir is improving enforcement workflows and counterfeit triage.",
        hook_strategy="domain_hook",
        company="Palantir",
        risk_surface="marketplaces",
    )

    assert "scales its enterprise ai initiatives" not in sanitized.lower()


def test_sanitize_generic_ai_opener_allows_pattern_when_research_anchored():
    text = (
        "As Palantir scales its enterprise AI initiatives, their team is balancing quality and speed. "
        "Zeal 2.0 helps prioritize enforcement work."
    )
    sanitized = sanitize_generic_ai_opener(
        text,
        research_text="As Palantir scales its enterprise AI initiatives, the company is tightening controls.",
        hook_strategy="research_anchored",
        company="Palantir",
        risk_surface="marketplaces",
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
