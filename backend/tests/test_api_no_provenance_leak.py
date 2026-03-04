from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from app.server import app, state


client = TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-EmailDJ-Beta-Key": "dev-beta-key"}


def test_stream_payload_does_not_include_internal_prompt_trace_fields() -> None:
    original_settings = state.settings
    try:
        state.settings = replace(original_settings, debug_prompt=True, llm_drafting_enabled=False)
        payload = {
            "prospect": {
                "name": "Alex Doe",
                "title": "Head of Brand Protection",
                "company": "Acme",
            },
            "research_text": "Acme expanded trademark enforcement coverage in Q1.",
            "offer_lock": "Trademark Workflow Platform",
            "cta_offer_lock": "Open to a quick chat to see if this is relevant?",
            "response_contract": "email_json_v1",
            "style_profile": {
                "formality": 0.1,
                "orientation": 0.0,
                "length": -0.3,
                "assertiveness": 0.1,
            },
            "company_context": {
                "company_name": "Example Seller",
                "current_product": "Trademark Workflow Platform",
                "seller_offerings": "Trademark monitoring\nMarketplace takedowns",
                "internal_modules": "Prospect Enrichment\nSequence QA",
                "company_notes": "Supports legal teams with trademark and infringement workflows.",
            },
        }
        accepted = client.post("/web/v1/generate", json=payload, headers=_headers())
        assert accepted.status_code == 200

        stream_res = client.get(accepted.json()["stream_url"], headers=_headers())
        assert stream_res.status_code == 200
        body = stream_res.text

        assert "prompt_trace" not in body
        assert "assembled_messages" not in body
        assert "selected_template_or_beat_ids" not in body
        assert "internal_modules" not in body
    finally:
        state.settings = original_settings
