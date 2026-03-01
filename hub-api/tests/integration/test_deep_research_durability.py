import asyncio
import importlib
import os

import pytest


@pytest.mark.asyncio
async def test_deep_research_job_lifecycle_and_restart_safe_load():
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ['REDIS_FORCE_INMEMORY'] = '1'

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        start = await client.post('/research/', json={'account_id': 'acc-1', 'domain': 'acme.com', 'company_name': 'Acme'})
        assert start.status_code == 200
        job_id = start.json()['job_id']

        status_payload = None
        for _ in range(20):
            status = await client.get(f'/research/{job_id}/status')
            assert status.status_code == 200
            status_payload = status.json()
            if status_payload.get('status') == 'complete':
                break
            await asyncio.sleep(0.01)

    assert status_payload is not None
    assert status_payload['status'] == 'complete'
    assert status_payload['job_id'] == job_id
    assert status_payload['result']['icp_fit_score'] >= 1

    mod = importlib.import_module('api.routes.deep_research')
    reloaded = importlib.reload(mod)
    persisted = await reloaded._load_job(job_id)
    assert persisted is not None
    assert persisted['status'] == 'complete'
    assert persisted['job_id'] == job_id
