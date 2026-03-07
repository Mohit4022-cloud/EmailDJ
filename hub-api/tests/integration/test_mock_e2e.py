import os

import pytest


@pytest.mark.asyncio
async def test_mock_e2e_quick_generate_stream_done():
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ['USE_PROVIDER_STUB'] = '1'
    os.environ['REDIS_FORCE_INMEMORY'] = '1'

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        payload = {
            'payload': {
                'accountId': '001-test',
                'accountName': 'Acme',
                'industry': 'SaaS',
                'notes': ['Budget is $200k in Q2'],
                'activityTimeline': [],
            }
        }

        ing = await client.post('/vault/ingest', json=payload)
        assert ing.status_code == 200

        start = await client.post('/generate/quick', json={'payload': payload['payload'], 'slider_value': 5})
        assert start.status_code == 200
        request_id = start.json()['request_id']

        stream = await client.get(f'/generate/stream/{request_id}')
        assert stream.status_code == 200
        assert 'event: start' in stream.text
        assert 'event: done' in stream.text
