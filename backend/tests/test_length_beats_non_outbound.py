from __future__ import annotations

import pytest

from app.engine import normalize_generate_request, run_engine
from app.schemas import WebCompanyContext, WebGenerateRequest, WebProspectInput, WebStyleProfile


CONTAMINATION_TOKENS = (
    "outbound execution",
    "reply quality",
    "first-touch",
    "manual review",
    "messaging logic",
    "example sequence",
)


def _request(*, category: str, length: float) -> WebGenerateRequest:
    if category == "brand_protection":
        product = "Trademark Enforcement"
        notes = "Supports legal teams with trademark and infringement case handling."
        research = "The account expanded trademark monitoring and anti-counterfeit operations."
    else:
        product = "Workflow Coordination Platform"
        notes = "Supports operational teams with reliable handoffs and execution visibility."
        research = "The account is improving cross-team workflow reliability this quarter."

    return WebGenerateRequest(
        prospect=WebProspectInput(
            name="Taylor Kim",
            title="Operations Director",
            company="Northstar",
            company_url="https://northstar.example",
            linkedin_url=None,
        ),
        prospect_first_name="Taylor",
        research_text=research,
        offer_lock=product,
        cta_offer_lock="Open to a quick chat to see if this is relevant?",
        response_contract="email_json_v1",
        style_profile=WebStyleProfile(formality=0.1, orientation=0.1, length=length, assertiveness=0.1),
        company_context=WebCompanyContext(
            company_name="Example Seller",
            current_product=product,
            seller_offerings="Offer A\nOffer B",
            internal_modules="Prospect Enrichment\nSequence QA",
            company_notes=notes,
            cta_offer_lock="Open to a quick chat to see if this is relevant?",
            cta_type="question",
        ),
    )


def _assert_fail_closed(category: str) -> None:
    for length in (-0.8, 0.0, 0.8):
        ctx = normalize_generate_request(_request(category=category, length=length))
        with pytest.raises(RuntimeError, match="ai_only_pipeline_requires_openai"):
            run_engine(ctx, max_repairs=2)


def test_length_progression_brand_protection_requires_ai_provider() -> None:
    _assert_fail_closed("brand_protection")


def test_length_progression_generic_b2b_requires_ai_provider() -> None:
    _assert_fail_closed("generic_b2b")
