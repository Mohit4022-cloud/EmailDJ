import time

from fastapi.testclient import TestClient

from app.server import app


client = TestClient(app)


def test_research_async_flow_returns_job_and_completes() -> None:
    created = client.post(
        "/research/",
        json={
            "account_id": "acme-001",
            "domain": "acme.com",
            "company_name": "Acme",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert payload["status"] == "queued"
    job_id = payload["job_id"]

    deadline = time.time() + 10
    while True:
        status = client.get(f"/research/{job_id}/status")
        assert status.status_code == 200
        body = status.json()
        if body["status"] in {"complete", "failed"}:
            break
        if time.time() >= deadline:
            raise AssertionError("research job did not complete in time")
        time.sleep(0.1)

    assert body["status"] == "complete"
    assert isinstance(body.get("result"), dict)
    assert "summary" in body["result"]


def test_research_status_not_found() -> None:
    res = client.get("/research/not-a-real-job/status")
    assert res.status_code == 404
