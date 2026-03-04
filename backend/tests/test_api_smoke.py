from fastapi.testclient import TestClient

from app.server import app


client = TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-EmailDJ-Beta-Key": "dev-beta-key"}


def test_generate_stream_smoke() -> None:
    payload = {
        "prospect": {
            "name": "Alex Doe",
            "title": "VP RevOps",
            "company": "Acme",
            "linkedin_url": "https://linkedin.com/in/alex",
        },
        "research_text": "Acme announced a RevOps initiative in January 2026 focused on pipeline efficiency.",
        "offer_lock": "Remix Studio",
        "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
        "style_profile": {
            "formality": 0,
            "orientation": 0,
            "length": -0.5,
            "assertiveness": 0,
        },
        "company_context": {
            "company_name": "Example Seller",
            "seller_offerings": "Workflow QA\nExecution analytics",
            "internal_modules": "Prospect Enrichment\nSequence QA",
            "company_notes": "Used by operations teams for message consistency controls.",
        },
    }
    res = client.post("/web/v1/generate", json=payload, headers=_headers())
    assert res.status_code == 200
    accepted = res.json()
    stream_res = client.get(accepted["stream_url"], headers=_headers())
    assert stream_res.status_code == 200
    body = stream_res.text
    assert "event: done" in body
    assert '"ok": false' in body
    assert '"error":' in body
    assert '"subject":' not in body
    assert '"body":' not in body


def test_generate_email_json_v1_done_contract() -> None:
    payload = {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
        },
        "research_text": "Acme launched a new workflow initiative in February 2026.",
        "offer_lock": "Remix Studio",
        "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
        "response_contract": "email_json_v1",
        "style_profile": {
            "formality": 0.1,
            "orientation": -0.2,
            "length": -0.3,
            "assertiveness": 0.2,
        },
        "company_context": {
            "company_name": "Corsearch",
            "seller_offerings": "Trademark monitoring\nMarketplace takedowns",
            "internal_modules": "Prospect Enrichment\nSequence QA",
            "company_notes": "Corsearch helps legal teams improve brand enforcement coverage.",
        },
    }
    accepted = client.post("/web/v1/generate", json=payload, headers=_headers())
    assert accepted.status_code == 200
    stream_res = client.get(accepted.json()["stream_url"], headers=_headers())
    assert stream_res.status_code == 200
    text = stream_res.text
    assert '"ok": false' in text
    assert '"error":' in text
    assert '"subject":' not in text
    assert '"body":' not in text


def test_preset_preview_batch_smoke() -> None:
    payload = {
        "prospect": {
            "name": "Alex Doe",
            "title": "SDR Manager",
            "company": "Acme",
            "company_url": "https://acme.com",
            "linkedin_url": "https://linkedin.com/in/alex",
        },
        "prospect_first_name": "Alex",
        "product_context": {
            "product_name": "Remix Studio",
            "one_line_value": "improve enforcement workflow consistency",
            "proof_points": ["Trademark monitoring", "Marketplace takedowns"],
            "target_outcome": "15-minute meeting",
        },
        "raw_research": {
            "deep_research_paste": "Acme launched enforcement workflow initiatives in January 2026.",
            "company_notes": "Corsearch helps legal teams improve enforcement workflow consistency.",
            "extra_constraints": None,
        },
        "global_sliders": {"formality": 45, "brevity": 65, "directness": 70, "personalization": 75},
        "presets": [
            {"preset_id": "challenger", "label": "The Challenger", "slider_overrides": {"directness": 85, "brevity": 75}},
            {"preset_id": "warm_intro", "label": "The Warm Intro", "slider_overrides": {"formality": 55, "personalization": 80}},
        ],
        "offer_lock": "Remix Studio",
        "cta_lock": "Open to a quick chat to see if this is relevant?",
        "cta_lock_text": None,
        "cta_type": "question",
        "hook_strategy": "research_anchored",
    }
    res = client.post("/web/v1/preset-previews/batch", json=payload, headers=_headers())
    assert res.status_code == 200
    data = res.json()
    assert len(data["previews"]) == 2
    assert data["previews"][0]["subject"] is None
    assert data["previews"][0]["body"] is None
    assert isinstance(data["previews"][0]["error"], dict)


def test_target_enrichment_requires_anchor() -> None:
    res = client.post("/web/v1/enrich/target", json={}, headers=_headers())
    assert res.status_code == 422


def test_web_debug_config_requires_beta_header() -> None:
    res = client.get("/web/v1/debug/config")
    assert res.status_code == 401
