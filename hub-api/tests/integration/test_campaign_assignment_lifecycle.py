import os

import pytest


@pytest.mark.asyncio
async def test_campaign_assignment_lifecycle_and_send():
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        create = await client.post('/campaigns/', json={'command': 'Target SaaS accounts', 'campaign_name': 'Q2 SaaS'})
        assert create.status_code == 200
        campaign_id = create.json()['campaign_id']

        approve = await client.post(f'/campaigns/{campaign_id}/approve', json={})
        assert approve.status_code == 200

        assign = await client.post(f'/campaigns/{campaign_id}/assign', json={'sdr_ids': ['demo-sdr']})
        assert assign.status_code == 200
        assignment_id = assign.json()['assignment_ids'][0]

        poll = await client.get('/assignments/poll?sdr_id=demo-sdr')
        assert poll.status_code == 200
        assert poll.json()['count'] >= 1

        accept = await client.post(f'/assignments/{assignment_id}/accept')
        assert accept.status_code == 200

        send = await client.post('/webhooks/send', json={'assignment_id': assignment_id, 'email_draft': 'draft'})
        assert send.status_code == 200


@pytest.mark.asyncio
async def test_blast_radius_requires_confirm():
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')

    from main import app
    from api.routes import campaigns as campaigns_mod

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        create = await client.post('/campaigns/', json={'command': 'Broad enterprise campaign', 'campaign_name': 'Big Blast'})
        campaign_id = create.json()['campaign_id']

        # Force threshold condition by mutating in-memory campaign for test.
        campaigns_mod._CAMPAIGNS[campaign_id]['audience'] = [{'id': str(i)} for i in range(campaigns_mod.BLAST_RADIUS_CONFIRM_THRESHOLD + 1)]

        bad = await client.post(f'/campaigns/{campaign_id}/approve', json={})
        assert bad.status_code == 400
        assert bad.json()['detail']['error'] == 'blast_radius_confirmation_required'

        ok = await client.post(f'/campaigns/{campaign_id}/approve', json={'confirm': 'CONFIRM'})
        assert ok.status_code == 200
