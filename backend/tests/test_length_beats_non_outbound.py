from __future__ import annotations

from app.engine import assembled_prompt_messages, normalize_generate_request, run_engine
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


def _collect(category: str) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for length in (-0.8, 0.0, 0.8):
        ctx = normalize_generate_request(_request(category=category, length=length))
        result = run_engine(ctx, max_repairs=2)
        messages = assembled_prompt_messages(ctx, result.plan)
        merged = f"{messages}\n{result.draft.subject}\n{result.draft.body}".lower()
        for token in CONTAMINATION_TOKENS:
            assert token not in merged
        rows.append((len(result.draft.selected_beat_ids), result.draft.body))
    return rows


def test_length_progression_brand_protection_no_outbound_contamination() -> None:
    rows = _collect("brand_protection")
    assert rows[1][0] >= rows[0][0]
    assert rows[2][0] >= rows[1][0]
    assert rows[2][0] > rows[0][0]


def test_length_progression_generic_b2b_no_outbound_contamination() -> None:
    rows = _collect("generic_b2b")
    assert rows[1][0] >= rows[0][0]
    assert rows[2][0] >= rows[1][0]
    assert rows[2][0] > rows[0][0]
