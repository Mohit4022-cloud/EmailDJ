import asyncio

import pytest

from context_vault.models import AccountContext


@pytest.mark.asyncio
async def test_extract_parses_core_fields_and_merges(monkeypatch):
    from context_vault import extractor

    async def fake_get_or_fetch(_account_id):
        return None

    captured = {}

    def fake_merge(existing, new_ctx):
        captured['existing'] = existing
        captured['new'] = new_ctx
        return new_ctx

    async def fake_embed_and_store(context, account_id):
        captured['embed_context_id'] = context.account_id
        captured['embed_account_id'] = account_id

    created_tasks = []
    original_create_task = asyncio.create_task

    def fake_create_task(coro):
        task = original_create_task(coro)
        created_tasks.append(task)
        return task

    monkeypatch.setattr('context_vault.extractor.cache.get_or_fetch', fake_get_or_fetch)
    monkeypatch.setattr('context_vault.extractor.merger.merge', fake_merge)
    monkeypatch.setattr('context_vault.extractor.embedder.embed_and_store', fake_embed_and_store)
    monkeypatch.setattr('context_vault.extractor.asyncio.create_task', fake_create_task)

    notes = (
        '<div>Acme SaaS has 450 employees. CFO Jane Doe said budget is $250k and '
        'the team wants to schedule demo in Q3 2026. Contact: jane.doe@acme.com</div>'
    )
    out = await extractor.extract(notes, 'acme-001')

    assert isinstance(out, AccountContext)
    assert out.account_id == 'acme-001'
    assert out.industry == 'SaaS'
    assert out.employee_count == 450
    assert out.budget == '$250k'
    assert out.timing == 'Q3 2026'
    assert out.next_action == 'Schedule demo'
    assert out.domain == 'acme.com'
    assert 'CFO' in out.decision_makers[0]
    assert any(c.email == 'jane.doe@acme.com' for c in out.extracted_contacts)

    await asyncio.gather(*created_tasks)
    assert captured['embed_context_id'] == 'acme-001'
    assert captured['embed_account_id'] == 'acme-001'
