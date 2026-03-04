from __future__ import annotations

from app.engine import assembled_prompt_messages, normalize_generate_request, run_engine
from app.schemas import WebCompanyContext, WebGenerateRequest, WebProspectInput, WebStyleProfile


def _request() -> WebGenerateRequest:
    return WebGenerateRequest(
        prospect=WebProspectInput(
            name="Jordan Lee",
            title="Head of Brand Protection",
            company="RetailCo",
            company_url="https://retailco.example",
            linkedin_url=None,
        ),
        prospect_first_name="Jordan",
        research_text="RetailCo expanded trademark enforcement and anti-counterfeit action this quarter.",
        offer_lock="Trademark Workflow Platform",
        cta_offer_lock="Open to a quick chat next week?",
        response_contract="email_json_v1",
        style_profile=WebStyleProfile(formality=0.1, orientation=0.1, length=-0.2, assertiveness=0.2),
        company_context=WebCompanyContext(
            company_name="Example Seller",
            current_product="Brand Protection",
            seller_offerings="Trademark monitoring\nMarketplace takedowns",
            internal_modules="Prospect Enrichment\nSequence QA\nPersona Research",
            company_notes="Supports legal and brand teams with enforcement workflows.",
            cta_offer_lock="Open to a quick chat next week?",
            cta_type="question",
        ),
    )


def test_internal_modules_are_excluded_from_assembled_payload_plan_and_draft() -> None:
    req = _request()
    ctx = normalize_generate_request(req)
    result = run_engine(ctx, max_repairs=2)
    messages = assembled_prompt_messages(ctx, result.plan)

    assert ctx.internal_modules == ["Prospect Enrichment", "Sequence QA", "Persona Research"]
    assert "Prospect Enrichment" not in ctx.proof_points
    assert "Sequence QA" not in ctx.proof_points
    assert "Persona Research" not in ctx.proof_points

    serialized_messages = str(messages)
    assert "Prospect Enrichment" not in serialized_messages
    assert "Sequence QA" not in serialized_messages
    assert "Persona Research" not in serialized_messages

    merged = f"{result.plan.value_prop}\n{result.draft.subject}\n{result.draft.body}"
    assert "Prospect Enrichment" not in merged
    assert "Sequence QA" not in merged
    assert "Persona Research" not in merged
