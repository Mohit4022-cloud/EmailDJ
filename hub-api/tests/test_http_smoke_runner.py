from __future__ import annotations

import json

from devtools.http_smoke_runner import _build_scorecard, _extract_stream, _load_pack


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


def test_load_pack_reads_custom_path(tmp_path):
    pack = {
        "_meta": {"presets": ["straight_shooter"], "slider_configs": {"medium": {"formality": 0.0, "orientation": 0.0, "length": 0.0, "assertiveness": 0.0}}},
        "seller": {"company_name": "Corsearch", "offer_lock": "Trademark Search, Screening, and Brand Protection", "cta_offer_lock": "Open to a quick 15-minute chat next week?", "cta_type": "time_ask"},
        "companies": [],
    }
    path = tmp_path / "custom_pack.json"
    path.write_text(json.dumps(pack), encoding="utf-8")

    loaded = _load_pack(path)
    assert loaded == pack


def test_build_scorecard_passes_seller_company_for_vendor_mismatch_ownership_check():
    case = _case()
    case["seller"]["company_name"] = "Corsearch"
    case["company"]["name"] = "Palantir"
    case["persona"]["title"] = "Head of Brand Risk"

    result = {
        "case": case,
        "email_text": "Subject: Test\n\nHi Alex, we can strengthen your brand protection this quarter.",
        "error": None,
        "stream_error": {},
        "stream_error_event_seen": False,
    }

    scorecard = _build_scorecard(result)
    assert "FAIL_PROSPECT_OWNS_OFFER" in scorecard["fail_tags"]
