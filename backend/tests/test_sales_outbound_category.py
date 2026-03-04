from __future__ import annotations

from app.engine import normalize_generate_request, run_engine
from app.schemas import WebCompanyContext, WebGenerateRequest, WebProspectInput, WebStyleProfile


def test_sales_outbound_category_still_generates_outbound_relevant_copy() -> None:
    req = WebGenerateRequest(
        prospect=WebProspectInput(
            name="Avery Hill",
            title="SDR Manager",
            company="Acme",
            company_url="https://acme.example",
            linkedin_url=None,
        ),
        prospect_first_name="Avery",
        research_text="Acme is scaling outbound prospecting with a focus on meeting conversion.",
        offer_lock="Outbound Workflow Assistant",
        cta_offer_lock="Open to a quick chat to see if this is relevant?",
        response_contract="email_json_v1",
        style_profile=WebStyleProfile(formality=0.0, orientation=-0.3, length=-0.2, assertiveness=0.1),
        company_context=WebCompanyContext(
            company_name="Example Seller",
            current_product="Outbound Sequencing Platform",
            seller_offerings="Sequencing assistant\nReply optimization",
            internal_modules="",
            company_notes="Built for SDR and RevOps teams that manage high-volume outreach.",
            cta_offer_lock="Open to a quick chat to see if this is relevant?",
            cta_type="question",
        ),
    )

    ctx = normalize_generate_request(req)
    result = run_engine(ctx, max_repairs=2)

    assert ctx.product_category == "sales_outbound"
    merged = f"{result.plan.value_prop}\n{result.draft.body}".lower()
    assert "outreach" in merged or "response" in merged
