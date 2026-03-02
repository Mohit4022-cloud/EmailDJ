from email_generation.output_enforcement import sanitize_generic_ai_opener


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
