from __future__ import annotations

from devtools.http_smoke_runner import _build_scorecard, _extract_stream


def _case() -> dict:
    return {
        "case_id": "acme__ceo__c_suite_sniper__medium",
        "company": {"id": "acme", "name": "Acme Consumer Brands"},
        "persona": {"id": "ceo", "name": "Sarah Chen", "title": "CEO", "persona_type": "exec"},
        "seller": {
            "offer_lock": "Trademark Search, Screening, and Brand Protection",
            "cta_offer_lock": "Open to a quick 15-minute chat next week?",
        },
        "preset_id": "c_suite_sniper",
        "slider_name": "medium",
        "slider_config": {"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0},
    }


def test_extract_stream_returns_error_payload():
    stream_text = (
        'event: start\n'
        'data: {"request_id":"r1"}\n\n'
        'event: error\n'
        'data: {"error":"ctco_validation_failed: offer_lock_missing"}\n\n'
    )

    rendered, done, err = _extract_stream(stream_text)
    assert rendered == ""
    assert done == {}
    assert err["error"] == "ctco_validation_failed: offer_lock_missing"


def test_build_scorecard_prefers_error_over_empty_email():
    result = {
        "case": _case(),
        "email_text": "",
        "error": "SSE error: ctco_validation_failed: offer_lock_missing",
        "stream_error": {"error": "ctco_validation_failed: offer_lock_missing"},
        "stream_error_event_seen": True,
    }

    scorecard = _build_scorecard(result)
    assert scorecard["fail_tags"] == ["ERROR"]
    assert "Runner error" in scorecard["notes"][0]
