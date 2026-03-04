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
            "company_name": "EmailDJ",
            "company_notes": "Used by outbound teams for message quality controls.",
        },
    }
    res = client.post("/web/v1/generate", json=payload, headers=_headers())
    assert res.status_code == 200
    accepted = res.json()
    stream_res = client.get(accepted["stream_url"], headers=_headers())
    assert stream_res.status_code == 200
    body = stream_res.text
    assert "event: done" in body
    assert "Subject:" in body


def test_target_enrichment_requires_anchor() -> None:
    res = client.post("/web/v1/enrich/target", json={}, headers=_headers())
    assert res.status_code == 422

