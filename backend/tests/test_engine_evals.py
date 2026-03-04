from __future__ import annotations

from app.engine import normalize_generate_request, run_engine
from app.schemas import WebCompanyContext, WebGenerateRequest, WebProspectInput, WebStyleProfile


FORBIDDEN_META = (
    "repeated_sentence_detected",
    "word_count_out_of_band",
    "subject",
    "body",
    "why it works",
    "unsupported claims",
    "role-specific relevance",
    "validator",
    "rubric",
)


FIXTURES = [
    {
        "name": "brand_protection_short",
        "research": "RetailCo expanded trademark enforcement operations in January 2026.",
        "length": -0.7,
        "cta": "Open to a quick chat to see if this is relevant?",
    },
    {
        "name": "brand_protection_medium",
        "research": "RetailCo posted updates on anti-counterfeit workflows across marketplaces.",
        "length": -0.2,
        "cta": "Open to a quick chat to see if this is relevant?",
    },
    {
        "name": "brand_protection_long",
        "research": "RetailCo announced new IP enforcement coordination across legal and operations teams.",
        "length": 0.6,
        "cta": "Open to a quick chat to see if this is relevant?",
    },
    {
        "name": "strict_cta_lock",
        "research": "RetailCo added a new global brand protection lead this month.",
        "length": -0.1,
        "cta": "Would you be open to a 15-minute working session next week?",
    },
    {
        "name": "challenger_preset",
        "research": "RetailCo is reviewing trademark escalation process quality this quarter.",
        "preset": "challenger",
        "length": -0.3,
        "cta": "Open to a quick chat to see if this is relevant?",
    },
]


def _request_from_fixture(fixture: dict) -> WebGenerateRequest:
    research = fixture.get("research") or "Research is limited in this context."
    return WebGenerateRequest(
        prospect=WebProspectInput(
            name="Alex Doe",
            title="Head of Brand Protection",
            company="RetailCo",
            company_url="https://retailco.example",
            linkedin_url="https://linkedin.com/in/alex",
        ),
        prospect_first_name="Alex",
        research_text=research,
        offer_lock="Trademark Workflow Platform",
        cta_offer_lock=fixture.get("cta") or "Open to a quick chat to see if this is relevant?",
        cta_type="question",
        preset_id=fixture.get("preset") or "straight_shooter",
        response_contract="email_json_v1",
        style_profile=WebStyleProfile(
            formality=float(fixture.get("formality", 0.1)),
            orientation=float(fixture.get("orientation", -0.2)),
            length=float(fixture.get("length", -0.3)),
            assertiveness=float(fixture.get("assertiveness", 0.2)),
        ),
        company_context=WebCompanyContext(
            company_name="Example Seller",
            company_url="https://example-seller.test",
            current_product="Trademark Workflow Platform",
            seller_offerings="Trademark monitoring\nMarketplace takedowns",
            internal_modules="Prospect Enrichment\nSequence QA",
            company_notes=fixture.get("company_notes") or "Supports legal and brand teams with consistent enforcement workflows.",
            cta_offer_lock=fixture.get("cta") or "Open to a quick chat to see if this is relevant?",
            cta_type="question",
        ),
    )


def test_engine_eval_fixtures_hard_fail_guards() -> None:
    for fixture in FIXTURES:
        req = _request_from_fixture(fixture)
        ctx = normalize_generate_request(req)
        result = run_engine(ctx, max_repairs=2)

        subject = result.draft.subject.strip()
        body = result.draft.body.strip()
        merged = f"{subject}\n{body}".lower()

        assert subject, fixture["name"]
        assert body, fixture["name"]
        assert body.splitlines()[-1].strip() == req.cta_offer_lock, fixture["name"]

        for token in FORBIDDEN_META:
            assert token not in merged, f"{fixture['name']}: found forbidden token {token}"

        assert "cta_lock_exact_missing" not in result.debug.violations, fixture["name"]


def test_engine_eval_multiple_presets_different_outputs() -> None:
    base = _request_from_fixture(FIXTURES[0])
    req_a = base.model_copy(update={"preset_id": "challenger"})
    req_b = base.model_copy(update={"preset_id": "warm_intro"})

    out_a = run_engine(normalize_generate_request(req_a), max_repairs=2)
    out_b = run_engine(normalize_generate_request(req_b), max_repairs=2)

    assert out_a.draft.subject != out_b.draft.subject or out_a.draft.body != out_b.draft.body
