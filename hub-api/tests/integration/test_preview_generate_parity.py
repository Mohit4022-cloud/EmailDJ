import json
import os
import re
from pathlib import Path
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2]))

_ROOT = Path(__file__).resolve().parents[2]
_PARITY_IDS_PATH = _ROOT / "evals" / "parity_ids.json"
_FULL_DATASET_PATH = _ROOT / "evals" / "gold_set.full.json"


def _headers() -> dict[str, str]:
    return {"x-emaildj-beta-key": "test-key"}


def _load_parity_cases() -> list[dict]:
    case_ids = json.loads(_PARITY_IDS_PATH.read_text(encoding="utf-8"))
    full = json.loads(_FULL_DATASET_PATH.read_text(encoding="utf-8"))
    by_id = {item["id"]: item for item in full}
    selected = [by_id[case_id] for case_id in case_ids]
    assert 10 <= len(selected) <= 20
    return selected


def _parse_sse_events(stream_text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    event_name = "message"
    for line in stream_text.splitlines():
        if line.startswith("event: "):
            event_name = line[7:].strip() or "message"
            continue
        if line.startswith("data: "):
            events.append((event_name, json.loads(line[6:])))
    return events


def _stream_token_text(events: list[tuple[str, dict]]) -> str:
    return "".join(payload.get("token", "") for event, payload in events if event == "token")


def _extract_body(draft: str) -> str:
    text = (draft or "").replace("\r\n", "\n")
    marker = "\nBody:\n"
    if marker in text:
        return text.split(marker, 1)[1].strip()
    lines = text.splitlines()
    return "\n".join(lines[1:]).strip() if len(lines) > 1 else ""


def _assert_lock_contract(text: str, offer_lock: str, cta_lock: str, forbidden_products: list[str]) -> None:
    lowered = text.lower()
    assert offer_lock.lower() in lowered
    for forbidden in forbidden_products:
        assert forbidden.lower() not in lowered

    body = _extract_body(text)
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    cta_count = sum(1 for line in lines if line == cta_lock)
    assert cta_count == 1
    assert lines[-1] == cta_lock


def _assert_greeting_first_name(text: str, expected_first_name: str) -> None:
    body = _extract_body(text)
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    match = re.match(r"^(Hi|Hello|Hey)\s+([^,\n]+),", first_line)
    assert match is not None
    greeted_name = match.group(2).strip()
    assert greeted_name == expected_first_name
    assert " " not in greeted_name


def _assert_done_metadata(done_payload: dict, request_id: str, session_id: str) -> None:
    assert done_payload["request_id"] == request_id
    assert done_payload["session_id"] == session_id
    assert done_payload["mode"] in {"mock", "real"}
    assert isinstance(done_payload["provider"], str)
    assert isinstance(done_payload["model"], str)
    assert isinstance(done_payload["provider_attempt_count"], int)
    assert isinstance(done_payload["validator_attempt_count"], int)
    assert isinstance(done_payload["json_repair_count"], int)
    assert isinstance(done_payload["violation_retry_count"], int)
    assert isinstance(done_payload["repaired"], bool)
    assert isinstance(done_payload["violation_codes"], list)
    assert isinstance(done_payload["violation_count"], int)
    assert done_payload["enforcement_level"] in {"warn", "repair", "block"}
    assert isinstance(done_payload["repair_loop_enabled"], bool)


def _assert_preview_meta_parity(meta: dict, done_payload: dict) -> None:
    assert isinstance(meta["request_id"], str)
    assert meta["session_id"] is None
    assert meta["generation_mode"] == done_payload["mode"]
    assert meta["provider"] == done_payload["provider"]
    assert meta["model"] == done_payload["model"]
    assert isinstance(meta["provider_attempt_count"], int)
    assert isinstance(meta["validator_attempt_count"], int)
    assert isinstance(meta["repair_attempt_count"], int)
    assert isinstance(meta["repaired"], bool)
    assert isinstance(meta["violation_codes"], list)
    assert isinstance(meta["violation_count"], int)
    assert meta["enforcement_level"] == done_payload["enforcement_level"]
    assert meta["repair_loop_enabled"] == done_payload["repair_loop_enabled"]


@pytest.mark.parametrize("case", _load_parity_cases(), ids=lambda item: item["id"])
@pytest.mark.asyncio
async def test_preview_and_generate_share_lock_contract_in_mock_mode(case: dict):
    httpx = pytest.importorskip("httpx")
    pytest.importorskip("fastapi")

    offer_lock = case["offer_lock"]
    cta_lock = case["cta_lock"]
    forbidden_products = case["other_products"]

    os.environ.setdefault("CHROME_EXTENSION_ORIGIN", "chrome-extension://dev")
    os.environ["WEB_APP_ORIGIN"] = "http://localhost:5174"
    os.environ["REDIS_FORCE_INMEMORY"] = "1"
    os.environ["EMAILDJ_WEB_BETA_KEYS"] = "test-key"
    os.environ["EMAILDJ_WEB_RATE_LIMIT_PER_MIN"] = "300"
    os.environ["USE_PROVIDER_STUB"] = "1"
    os.environ["EMAILDJ_PRESET_PREVIEW_PIPELINE"] = "on"

    from main import app

    generate_payload = {
        "prospect": {
            "name": case["prospect"]["full_name"],
            "title": case["prospect"]["title"],
            "company": case["prospect"]["company"],
            "linkedin_url": "https://linkedin.com/in/test-prospect",
        },
        "research_text": case["research_text"],
        "offer_lock": offer_lock,
        "cta_offer_lock": cta_lock,
        "cta_type": case["cta_type"],
        "style_profile": case["style_profile"],
        "company_context": {
            "company_name": case["seller"]["company_name"],
            "company_url": case["seller"]["company_url"],
            "current_product": offer_lock,
            "other_products": ", ".join(forbidden_products),
            "company_notes": case["seller"]["company_notes"],
        },
    }

    preview_payload = {
        "prospect": {
            "name": case["prospect"]["full_name"],
            "title": case["prospect"]["title"],
            "company": case["prospect"]["company"],
            "company_url": "https://example.com",
            "linkedin_url": "https://linkedin.com/in/test-prospect",
        },
        "product_context": {
            "product_name": offer_lock,
            "one_line_value": f"improve outbound quality with {offer_lock}",
            "proof_points": case.get("approved_proof_points") or ["Workflow controls", "Message QA guardrails"],
            "target_outcome": "15-minute meeting",
        },
        "raw_research": {
            "deep_research_paste": case["research_text"],
            "company_notes": case["seller"]["company_notes"],
            "extra_constraints": None,
        },
        "global_sliders": {
            "formality": 45,
            "brevity": 65,
            "directness": 70,
            "personalization": 75,
        },
        "presets": [
            {"preset_id": "challenger", "label": "The Challenger", "slider_overrides": {"directness": 80}},
            {"preset_id": "warm_intro", "label": "The Warm Intro", "slider_overrides": {"formality": 55}},
        ],
        "offer_lock": offer_lock,
        "cta_lock": cta_lock,
    }

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/web/v1/generate", json=generate_payload, headers=_headers())
        assert start.status_code == 200
        start_body = start.json()
        request_id = start_body["request_id"]
        session_id = start_body["session_id"]

        stream = await client.get(f"/web/v1/stream/{request_id}", headers=_headers())
        assert stream.status_code == 200
        events = _parse_sse_events(stream.text)
        draft = _stream_token_text(events)
        _assert_lock_contract(draft, offer_lock, cta_lock, forbidden_products)
        _assert_greeting_first_name(draft, case["expected"]["greeting_first_name"])
        done_payload = next(payload for event, payload in events if event == "done")
        _assert_done_metadata(done_payload, request_id=request_id, session_id=session_id)

        preview_res = await client.post("/web/v1/preset-previews/batch", json=preview_payload, headers=_headers())
        assert preview_res.status_code == 200
        preview_body = preview_res.json()
        previews = preview_body["previews"]
        assert len(previews) == 2
        for item in previews:
            combined = f"Subject: {item['subject']}\nBody:\n{item['body']}"
            _assert_lock_contract(combined, offer_lock, cta_lock, forbidden_products)
            _assert_greeting_first_name(combined, case["expected"]["greeting_first_name"])

        _assert_preview_meta_parity(preview_body["meta"], done_payload)
