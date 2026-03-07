from __future__ import annotations

import json

from devtools.http_smoke_runner import _build_scorecard, _build_summary, _extract_stream, _load_pack


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


def test_build_summary_reports_provider_sources_and_remix_gates():
    case = _case()
    results = [
        {
            "case": case,
            "flow": "generate",
            "latency_ms": 120,
            "error": None,
            "done_payload": {
                "provider": "mock",
                "provider_source": "provider_stub",
                "violation_codes": [],
                "claims_policy_intervention_count": 0,
            },
            "response_json": {},
        },
        {
            "case": {**case, "preset_id": "headliner"},
            "flow": "remix",
            "latency_ms": 180,
            "error": None,
            "done_payload": {
                "provider": "openai",
                "provider_source": "external_provider",
                "violation_codes": ["length_out_of_range", "missing_required_field"],
                "claims_policy_intervention_count": 1,
            },
            "response_json": {},
        },
    ]
    scorecards = [
        {"case_id": case["case_id"], "pass": True, "fail_tags": [], "word_count": 72, "notes": []},
        {"case_id": "remix_case", "pass": False, "fail_tags": ["ERROR"], "word_count": 43, "notes": ["too short"]},
    ]

    summary = _build_summary("run-1", "smoke", results, scorecards, 12.4)

    assert summary["provider_source_counts"] == {"provider_stub": 1, "external_provider": 1}
    assert summary["route_pass_fail_counts"]["generate"] == {"total": 1, "pass": 1, "fail": 0}
    assert summary["route_pass_fail_counts"]["remix"] == {"total": 1, "pass": 0, "fail": 1}
    assert summary["required_field_miss_count"] == 1
    assert summary["under_length_miss_count"] == 1
    assert summary["claims_policy_intervention_count"] == 1
    assert summary["launch_gates"]["provider_green"] == "red"
    assert summary["launch_gates"]["remix_green"] == "red"
