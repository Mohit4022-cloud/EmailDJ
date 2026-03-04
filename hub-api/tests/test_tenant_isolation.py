"""Multi-seller isolation tests.

Parametrized across all seller fixtures to verify that ownership detection,
category-mismatch guardrails, and scorecard flags all behave correctly for
every registered seller — not just brand-protection sellers.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from devtools.fail_detectors import scorecard
from devtools.fixture_loader import list_sellers, load_seller

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_SELLERS = list_sellers()  # ["anthropic", "corsearch", "emaildj", "nike", "rippling"]


def _meta(seller: dict, **overrides) -> dict:
    base = {
        "prospect_name": "Jordan Smith",
        "prospect_company": "Acme",
        "prospect_title": "VP Sales",
        "seller_company": seller["seller_company_name"],
        "offer_lock": seller["offer_name"],
        "offer_category": seller.get("offer_category"),
        "preset_id": "straight_shooter",
        "cta_offer_lock": seller.get("cta_offer_lock", "Open to a 15-min chat next week?"),
    }
    base.update(overrides)
    return base


def _clean_body(offer_lock: str) -> str:
    """A structurally clean email that should produce no fail tags."""
    return (
        f"Hi Jordan, Acme is scaling its outbound motion and tightening quality controls this quarter. "
        f"{offer_lock} gives your team a consistent way to reduce message drift while keeping reps moving fast. "
        f"Open to a 15-min chat next week?"
    )


# ---------------------------------------------------------------------------
# Tests: clean email passes for all sellers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seller_name", ALL_SELLERS)
def test_clean_email_passes_scorecard_for_all_sellers(seller_name: str):
    seller = load_seller(seller_name)
    meta = _meta(seller)
    body = _clean_body(seller["offer_name"])
    result = scorecard(f"tenant_clean_{seller_name}", body, meta)
    assert result["fail_tags"] == [], (
        f"Seller '{seller_name}': unexpected fail tags {result['fail_tags']} on clean body"
    )


# ---------------------------------------------------------------------------
# Tests: prospect-owns-offer detection for all sellers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("seller_name", ALL_SELLERS)
def test_prospect_ownership_detected_for_all_sellers(seller_name: str):
    seller = load_seller(seller_name)
    offer = seller["offer_name"]
    primary_keyword = offer.split(",")[0].strip()  # first comma-phrase, e.g. "Trademark Search"
    meta = _meta(seller, prospect_company="Acme")
    body = (
        f"Hi Jordan, we can improve {primary_keyword} for Acme and tighten {primary_keyword} at Acme. "
        f"Our analysis found Acme uses {primary_keyword} workflows inconsistently."
    )
    result = scorecard(f"tenant_ownership_{seller_name}", body, meta)
    assert "FAIL_PROSPECT_OWNS_OFFER" in result["fail_tags"], (
        f"Seller '{seller_name}': FAIL_PROSPECT_OWNS_OFFER not detected; fail_tags={result['fail_tags']}"
    )


@pytest.mark.parametrize("seller_name", ALL_SELLERS)
def test_your_offer_flagged_when_vendor_differs(seller_name: str):
    seller = load_seller(seller_name)
    offer = seller["offer_name"]
    primary_keyword = offer.split(",")[0].strip()
    # "your <keyword>" is possession language when seller != prospect
    body = f"Hi Jordan, we can strengthen your {primary_keyword} coverage this quarter."
    meta_different = _meta(seller, seller_company="AcmeDifferentVendor", prospect_company="Acme")
    meta_same = _meta(seller, seller_company="Acme", prospect_company="Acme")

    result_different = scorecard(f"tenant_your_offer_different_{seller_name}", body, meta_different)
    result_same = scorecard(f"tenant_your_offer_same_{seller_name}", body, meta_same)

    assert "FAIL_PROSPECT_OWNS_OFFER" in result_different["fail_tags"], (
        f"Seller '{seller_name}': 'your <offer>' should flag when vendor != prospect"
    )
    assert "FAIL_PROSPECT_OWNS_OFFER" not in result_same["fail_tags"], (
        f"Seller '{seller_name}': 'your <offer>' should not flag when vendor == prospect"
    )


# ---------------------------------------------------------------------------
# Tests: category-mismatch guardrails are domain-specific
# ---------------------------------------------------------------------------


def test_no_category_mismatch_for_hr_tech():
    seller = load_seller("rippling")
    assert seller.get("offer_category") == "hr_tech"
    # HR vocabulary in an HR seller email should not trigger mismatch
    body = (
        "Hi Jordan, Acme is tightening payroll governance and streamlining HRIS workflows. "
        "Our platform gives your ops team visibility across workforce management. "
        "Open to a quick chat?"
    )
    result = scorecard("tenant_no_mismatch_hr", body, _meta(seller))
    assert "FAIL_CATEGORY_MISMATCH" not in result["fail_tags"], (
        f"HR vocab should not trigger FAIL_CATEGORY_MISMATCH for hr_tech seller; "
        f"fail_tags={result['fail_tags']}"
    )


def test_category_mismatch_for_bp_offer_using_cyber_terms():
    seller = load_seller("corsearch")
    assert seller.get("offer_category") == "brand_protection"
    # Cybersecurity framing in a brand-protection email should trigger mismatch
    body = (
        "Hi Jordan, Acme is tightening its cybersecurity posture after a recent data breach. "
        "Our endpoint protection platform reduces your attack surface."
    )
    result = scorecard("tenant_mismatch_bp_cyber", body, _meta(seller))
    assert "FAIL_CATEGORY_MISMATCH" in result["fail_tags"], (
        f"Cyber vocab should trigger FAIL_CATEGORY_MISMATCH for brand_protection seller; "
        f"fail_tags={result['fail_tags']}"
    )


def test_no_category_mismatch_for_ai_platform():
    seller = load_seller("anthropic")
    assert seller.get("offer_category") == "ai_platform"
    # AI/LLM vocabulary in an AI platform email should not trigger mismatch
    body = (
        "Hi Jordan, Acme is evaluating LLM integrations to accelerate generative AI workflows. "
        "Our foundation model APIs give your team a reliable inference layer. "
        "Open to a quick chat?"
    )
    result = scorecard("tenant_no_mismatch_ai", body, _meta(seller))
    assert "FAIL_CATEGORY_MISMATCH" not in result["fail_tags"], (
        f"AI vocab should not trigger FAIL_CATEGORY_MISMATCH for ai_platform seller; "
        f"fail_tags={result['fail_tags']}"
    )
