import os

import pytest


@pytest.mark.asyncio
async def test_real_mode_provider_prompt_is_redacted(monkeypatch):
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ['EMAILDJ_QUICK_GENERATE_MODE'] = 'real'
    os.environ['EMAILDJ_REAL_PROVIDER'] = 'openai'
    os.environ['OPENAI_API_KEY'] = 'test-key'
    os.environ['REDIS_FORCE_INMEMORY'] = '1'

    from main import app
    from email_generation import quick_generate as qg

    captured = {}

    async def fake_openai(prompt, model_name, timeout=30.0):
        captured['prompt'] = prompt
        return 'Subject: Real mode response\n\nHello there.'

    monkeypatch.setattr(qg, '_openai_chat_completion', fake_openai)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        payload = {
            'payload': {
                'accountId': '001-real',
                'accountName': 'Acme',
                'notes': ['Contact me at jane.doe@example.com or 303-555-1212.'],
                'activityTimeline': [],
            },
            'slider_value': 5,
        }

        start = await client.post('/generate/quick', json=payload)
        assert start.status_code == 200
        request_id = start.json()['request_id']

        stream = await client.get(f'/generate/stream/{request_id}')
        assert stream.status_code == 200
        assert 'event: done' in stream.text

    prompt_text = ' '.join(m.get('content', '') for m in captured['prompt'])
    assert 'jane.doe@example.com' not in prompt_text
    assert '303-555-1212' not in prompt_text
