from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


def test_style_profile_is_clamped():
    from email_generation.remix_engine import normalize_style_profile

    normalized = normalize_style_profile(
        {
            "formality": 2.7,
            "orientation": -2.3,
            "length": 0.3,
            "assertiveness": -99,
        }
    )
    assert normalized == {
        "formality": 1.0,
        "orientation": -1.0,
        "length": 0.3,
        "assertiveness": -1.0,
    }


def test_style_directives_span_extremes():
    from email_generation.remix_engine import style_directives

    low = style_directives({"formality": -1, "orientation": -1, "length": -1, "assertiveness": -1})
    high = style_directives({"formality": 1, "orientation": 1, "length": 1, "assertiveness": 1})

    assert "conversational" in low["formality"]
    assert "pain/problem" in low["orientation"]
    assert "very short" in low["length"]
    assert "diplomatic" in low["assertiveness"]

    assert "formal" in high["formality"]
    assert "outcomes and upside" in high["orientation"]
    assert "expanded" in high["length"]
    assert "bold ask" in high["assertiveness"]


def test_style_profile_key_is_stable():
    from email_generation.remix_engine import style_profile_key

    key = style_profile_key({"formality": 0.123, "orientation": -0.987, "length": 0.1, "assertiveness": 0})
    assert key == "f:0.12|o:-0.99|l:0.10|a:0.00"


def test_factual_brief_and_anchors_include_prospect_facts():
    from email_generation.remix_engine import build_anchors, build_factual_brief

    prospect = {"name": "Alex", "title": "SDR Manager", "company": "Acme", "linkedin_url": "https://linkedin.com/in/alex"}
    brief = build_factual_brief(prospect, "Acme is hiring and modernizing outbound execution.")
    anchors = build_anchors(prospect)

    assert "Alex" in brief
    assert "Acme" in brief
    assert "LinkedIn URL" in brief
    assert "Acme" in anchors["intent"]
    assert "15-minute walkthrough" in anchors["cta"]


def test_company_context_brief_and_mapping_anchor_include_focus_product():
    from email_generation.remix_engine import build_anchors, build_company_context_brief

    company_context = {
        "company_name": "EmailDJ",
        "company_url": "https://emaildj.ai",
        "current_product": "Remix Studio",
        "other_products": "Prospect Enrichment, Sequence QA",
        "company_notes": "Built for SDR teams that need faster personalization with control.",
    }
    prospect = {"name": "Alex", "title": "SDR Manager", "company": "Acme", "linkedin_url": None}
    brief = build_company_context_brief(company_context)
    anchors = build_anchors(prospect, company_context=company_context)

    assert "EmailDJ" in brief
    assert "Remix Studio" in brief
    assert "Prospect Enrichment" in brief
    assert "Remix Studio" in anchors["service_mapping"]
