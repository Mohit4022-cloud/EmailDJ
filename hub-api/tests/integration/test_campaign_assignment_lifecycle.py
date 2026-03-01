import os

import pytest


@pytest.mark.asyncio
async def test_campaign_assignment_lifecycle_and_send():
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ.setdefault('REDIS_FORCE_INMEMORY', '1')

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
    os.environ.setdefault('REDIS_FORCE_INMEMORY', '1')

    from main import app
    from api.routes import campaigns as campaigns_mod

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        create = await client.post('/campaigns/', json={'command': 'Broad enterprise campaign', 'campaign_name': 'Big Blast'})
        campaign_id = create.json()['campaign_id']

        campaign = await campaigns_mod._load_campaign(campaign_id)
        campaign['audience'] = [{'id': str(i)} for i in range(campaigns_mod.BLAST_RADIUS_CONFIRM_THRESHOLD + 1)]
        await campaigns_mod._save_campaign(campaign)

        bad = await client.post(f'/campaigns/{campaign_id}/approve', json={})
        assert bad.status_code == 400
        assert bad.json()['detail']['error'] == 'blast_radius_confirmation_required'

        ok = await client.post(f'/campaigns/{campaign_id}/approve', json={'confirm': 'CONFIRM'})
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_campaign_create_and_approve_with_provider_stubs(monkeypatch):
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ.setdefault('REDIS_FORCE_INMEMORY', '1')
    os.environ['EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE'] = 'real'
    os.environ['SALESFORCE_INSTANCE_URL'] = 'https://crm.example.com'
    os.environ['SALESFORCE_ACCESS_TOKEN'] = 'token'
    os.environ['BOMBORA_API_KEY'] = 'token'

    from agents.nodes import crm_query_agent as crm_node
    from agents.nodes import intent_data_agent as intent_node
    from agents.providers import campaign_intelligence as providers
    from main import app

    class StubCRMProvider:
        name = 'salesforce'

        async def fetch_accounts(self, *, command: str) -> list[dict]:
            assert command
            return [
                {
                    'account_id': '001A',
                    'name': 'Acme Security',
                    'industry': 'SaaS',
                    'website': 'https://acme-security.example.com',
                },
                {
                    'account_id': '001B',
                    'name': 'No Intent Co',
                    'industry': 'SaaS',
                    'website': 'https://no-intent.example.com',
                },
            ]

    class StubIntentProvider:
        name = 'bombora'

        async def fetch_intent(self, *, domains: list[str], command: str) -> list[dict]:
            assert command
            assert 'acme-security.example.com' in domains
            return [
                {
                    'domain': 'acme-security.example.com',
                    'topics': ['pipeline'],
                    'surge_score': 88,
                    'data_source': 'bombora',
                    'as_of_date': '2026-03-01',
                }
            ]

    monkeypatch.setattr(crm_node, 'resolve_crm_provider_runtime', lambda: providers.ProviderRuntime(primary=StubCRMProvider(), fallback=None, mode='real'))
    monkeypatch.setattr(intent_node, 'resolve_intent_provider_runtime', lambda: providers.ProviderRuntime(primary=StubIntentProvider(), fallback=None, mode='real'))

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        create = await client.post('/campaigns/', json={'command': 'Prioritize accounts with buying signals', 'campaign_name': 'Intent Run'})
        assert create.status_code == 200
        assert create.json()['estimated_audience_size'] == 1
        campaign_id = create.json()['campaign_id']

        approve = await client.post(f'/campaigns/{campaign_id}/approve', json={})
        assert approve.status_code == 200
        assert approve.json()['status'] == 'sequences_ready'


@pytest.mark.asyncio
async def test_campaign_create_with_fallback_mode_uses_mock_on_provider_failure(monkeypatch):
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ.setdefault('REDIS_FORCE_INMEMORY', '1')
    os.environ['EMAILDJ_CAMPAIGN_INTELLIGENCE_MODE'] = 'fallback'
    os.environ['SALESFORCE_INSTANCE_URL'] = 'https://crm.example.com'
    os.environ['SALESFORCE_ACCESS_TOKEN'] = 'token'
    os.environ['BOMBORA_API_KEY'] = 'token'

    from agents.nodes import crm_query_agent as crm_node
    from agents.nodes import intent_data_agent as intent_node
    from agents.providers import campaign_intelligence as providers
    from main import app

    class FailingCRMProvider:
        name = 'salesforce'

        async def fetch_accounts(self, *, command: str) -> list[dict]:
            raise providers.ProviderExecutionError('stub crm outage')

    class FailingIntentProvider:
        name = 'bombora'

        async def fetch_intent(self, *, domains: list[str], command: str) -> list[dict]:
            raise providers.ProviderExecutionError('stub intent outage')

    monkeypatch.setattr(
        crm_node,
        'resolve_crm_provider_runtime',
        lambda: providers.ProviderRuntime(primary=FailingCRMProvider(), fallback=providers.MockCRMProvider(), mode='fallback'),
    )
    monkeypatch.setattr(
        intent_node,
        'resolve_intent_provider_runtime',
        lambda: providers.ProviderRuntime(primary=FailingIntentProvider(), fallback=providers.MockIntentProvider(), mode='fallback'),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        create = await client.post('/campaigns/', json={'command': 'Fallback coverage run', 'campaign_name': 'Fallback Run'})
        assert create.status_code == 200
        # Mock providers still produce non-empty audience in fallback mode.
        assert create.json()['estimated_audience_size'] > 0
