from __future__ import annotations

from dataclasses import replace
import logging

from fastapi.testclient import TestClient

from app.server import app, state


client = TestClient(app)


def _headers() -> dict[str, str]:
    return {"X-EmailDJ-Beta-Key": "dev-beta-key"}


def _generate_and_stream() -> None:
    payload = {
        "prospect": {
            "name": "Alex Doe",
            "title": "Head of Brand Protection",
            "company": "Acme",
        },
        "research_text": "Acme expanded trademark enforcement coverage this quarter.",
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
            "current_product": "Brand Protection",
            "seller_offerings": "Trademark monitoring\nMarketplace takedowns",
            "internal_modules": "Prospect Enrichment\nSequence QA",
            "company_notes": "Supports legal teams with trademark and infringement workflows.",
        },
    }
    accepted = client.post("/web/v1/generate", json=payload, headers=_headers())
    assert accepted.status_code == 200
    stream_res = client.get(accepted.json()["stream_url"], headers=_headers())
    assert stream_res.status_code == 200


def test_debug_prompt_logs_are_not_emitted_in_ai_orchestrator_mode(caplog) -> None:
    original_settings = state.settings
    try:
        caplog.set_level(logging.INFO)
        state.settings = replace(original_settings, debug_prompt=False)
        caplog.clear()
        _generate_and_stream()
        plain_logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "prompt_trace stage=normalize.generate" not in plain_logs
        assert "prompt_trace stage=provenance.generate" not in plain_logs

        state.settings = replace(original_settings, debug_prompt=True)
        caplog.clear()
        _generate_and_stream()
        debug_logs = "\n".join(record.getMessage() for record in caplog.records)
        assert "prompt_trace stage=normalize.generate" not in debug_logs
        assert "prompt_trace stage=plan.generate" not in debug_logs
        assert "prompt_trace stage=assembled_messages.generate" not in debug_logs
        assert "prompt_trace stage=provenance.generate" not in debug_logs
    finally:
        state.settings = original_settings
