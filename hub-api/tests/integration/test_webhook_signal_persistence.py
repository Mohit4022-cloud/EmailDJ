import os

import pytest


@pytest.mark.asyncio
async def test_webhook_signals_persist_in_redis_backing():
    httpx = pytest.importorskip('httpx')
    pytest.importorskip('fastapi')

    os.environ.setdefault('CHROME_EXTENSION_ORIGIN', 'chrome-extension://dev')
    os.environ['REDIS_FORCE_INMEMORY'] = '1'

    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
        edit = await client.post('/webhooks/edit', json={'original_draft': 'Hi', 'final_edit': 'Hi team'})
        assert edit.status_code == 200

        send = await client.post('/webhooks/send', json={'assignment_id': 'a-1', 'email_draft': 'draft text'})
        assert send.status_code == 200

        reply = await client.post('/webhooks/reply', json={'account_id': 'acc-1', 'contact_id': 'c-1', 'raw_payload': {'text': 'Thanks'}})
        assert reply.status_code == 200

    from api.routes import webhooks as webhooks_mod

    edit_rows = await webhooks_mod._load_signals('edit')
    send_rows = await webhooks_mod._load_signals('send')
    reply_rows = await webhooks_mod._load_signals('reply')

    assert len(edit_rows) >= 1
    assert len(send_rows) >= 1
    assert len(reply_rows) >= 1

    assert 'diff' in edit_rows[-1]
    assert 'prompt_evolution_flag' in edit_rows[-1]
    assert 'assignment_id' in send_rows[-1]
    assert 'sent_at' in send_rows[-1]
    assert reply_rows[-1]['raw_payload']['text'] == 'Thanks'
