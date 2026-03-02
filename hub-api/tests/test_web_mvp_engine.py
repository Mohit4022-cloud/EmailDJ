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


def test_style_profile_to_ctco_sliders_maps_minus1_to_plus1():
    from email_generation.remix_engine import style_profile_to_ctco_sliders

    sliders = style_profile_to_ctco_sliders(
        {
            "formality": -1.0,
            "orientation": 0.0,
            "length": 1.0,
            "assertiveness": -0.5,
        }
    )

    assert sliders == {
        "tone_formal_casual": 0,
        "framing_problem_outcome": 50,
        "length_short_long": 100,
        "stance_bold_diplomatic": 25,
    }


def test_body_word_range_bins_match_ctco_contract():
    from email_generation.remix_engine import body_word_range

    assert body_word_range(0) == (45, 70)
    assert body_word_range(21) == (70, 110)
    assert body_word_range(41) == (110, 160)
    assert body_word_range(61) == (160, 220)
    assert body_word_range(81) == (220, 300)


def test_style_profile_key_is_stable():
    from email_generation.remix_engine import style_profile_key

    key = style_profile_key({"formality": 0.123, "orientation": -0.987, "length": 0.1, "assertiveness": 0})
    assert key == "f:0.12|o:-0.99|l:0.10|a:0.00"


def test_factual_brief_and_anchors_include_lock_fields():
    from email_generation.remix_engine import build_anchors, build_factual_brief

    prospect = {"name": "Alex", "title": "SDR Manager", "company": "Acme", "linkedin_url": "https://linkedin.com/in/alex"}
    brief = build_factual_brief(prospect, "Acme is hiring and modernizing outbound execution.")
    anchors = build_anchors(prospect=prospect, offer_lock="Remix Studio", cta_lock="Open to a quick chat to see if this is relevant?")

    assert "Alex" in brief
    assert "Acme" in brief
    assert "LinkedIn URL" in brief
    assert anchors["offer_lock"] == "Remix Studio"
    assert anchors["cta_lock"] == "Open to a quick chat to see if this is relevant?"


def test_company_context_brief_includes_primary_offering_but_not_adjacent_list():
    from email_generation.remix_engine import build_company_context_brief

    company_context = {
        "company_name": "EmailDJ",
        "company_url": "https://emaildj.ai",
        "current_product": "Remix Studio",
        "other_products": "Prospect Enrichment, Sequence QA",
        "company_notes": "Built for SDR teams that need faster personalization with control.",
    }
    brief = build_company_context_brief(company_context)

    assert "EmailDJ" in brief
    assert "Remix Studio" in brief
    assert "Prospect Enrichment" not in brief
