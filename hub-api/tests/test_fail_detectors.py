from __future__ import annotations

from devtools.fail_detectors import scorecard


def _meta(**overrides):
    base = {
        "prospect_name": "Jordan Smith",
        "prospect_company": "Acme",
        "prospect_title": "VP Sales",
        "seller_company": "EmailDJ",
        "offer_lock": "Remix Studio",
        "offer_category": "revenue_intelligence",
        "preset_id": "straight_shooter",
        "cta_offer_lock": "Open to a quick 15-min chat to see if this is relevant?",
    }
    base.update(overrides)
    return base


def test_fail_prospect_owns_offer_detects_expanded_brand_patterns():
    # Stimulus: email incorrectly frames brand protection as Acme's asset.
    # Offer explicitly contains "Brand Protection" → detection must fire.
    body = (
        "Hi Jordan, we can improve brand protection for Acme and tighten brand protection at Acme. "
        "Our analysis found Acme uses brand protection workflows inconsistently."
    )
    result = scorecard(
        "case-1",
        body,
        _meta(
            prospect_company="Acme",
            offer_lock="Trademark Search, Screening, and Brand Protection",
            offer_category="brand_protection",
        ),
    )

    assert "FAIL_PROSPECT_OWNS_OFFER" in result["fail_tags"]
    notes = " ".join(result["notes"]).lower()
    assert "brand protection for acme" in notes
    assert "brand protection at acme" in notes
    assert "acme uses brand protection" in notes


def test_fail_prospect_owns_offer_flags_your_offer_only_when_vendor_differs():
    # "your Brand Protection" is ownership language when seller != prospect.
    body = "Hi Jordan, we can strengthen your brand protection coverage this quarter."

    different_vendor = scorecard(
        "case-2",
        body,
        _meta(
            seller_company="Corsearch",
            prospect_company="Acme",
            offer_lock="Brand Protection",
            offer_category="brand_protection",
        ),
    )
    same_vendor = scorecard(
        "case-3",
        body,
        _meta(
            seller_company="Acme",
            prospect_company="Acme",
            offer_lock="Brand Protection",
            offer_category="brand_protection",
        ),
    )

    assert "FAIL_PROSPECT_OWNS_OFFER" in different_vendor["fail_tags"]
    assert "FAIL_PROSPECT_OWNS_OFFER" not in same_vendor["fail_tags"]


def test_fail_double_greeting_detects_second_greeting_in_first_12_tokens():
    body = "Hi Jordan, Hello again and thanks for taking a look at this note."
    result = scorecard("case-4", body, _meta(prospect_title="Head of Revenue Operations"))

    assert "FAIL_DOUBLE_GREETING" in result["fail_tags"]


def test_fail_weak_cta_phrase_blocked_for_straight_shooter_and_allowed_for_giver_non_exec():
    body = (
        "Hi Jordan, quick note on outbound workflow quality.\n\n"
        "Open to a quick call? Worth a look / Not a priority?"
    )

    blocked = scorecard("case-5", body, _meta(preset_id="straight_shooter", prospect_title="Head of Revenue Operations"))
    allowed = scorecard("case-6", body, _meta(preset_id="giver", prospect_title="Head of Revenue Operations"))

    assert "FAIL_WEAK_CTA" in blocked["fail_tags"]
    assert "FAIL_WEAK_CTA" not in allowed["fail_tags"]
