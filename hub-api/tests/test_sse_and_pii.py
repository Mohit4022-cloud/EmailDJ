import asyncio

from email_generation.streaming import _event_generator
from pii.token_vault import detokenize, tokenize


async def _collect_events():
    async def gen():
        yield 'hello '
        yield 'world'

    items = []
    async for item in _event_generator('req-1', gen()):
        items.append(item)
    return items


def test_sse_event_order_and_shape():
    items = asyncio.run(_collect_events())
    assert items[0]['event'] == 'start'
    assert items[1]['event'] == 'token'
    assert items[2]['event'] == 'token'
    assert items[-1]['event'] == 'done'

    for item in items:
        assert 'request_id' in item['data']
        assert 'sequence' in item['data']
        assert 'timestamp' in item['data']


def test_token_vault_round_trip():
    source = 'Spoke to Alex on March 2026 about $200k at @example.com'
    tok = tokenize(source)
    restored = detokenize(tok.text, tok.vault)
    assert restored == source


def test_token_vault_repeated_values():
    source = 'Budget $200k and again $200k by March 2026 and March 2026'
    tok = tokenize(source)
    restored = detokenize(tok.text, tok.vault)
    assert restored == source


def test_token_vault_empty_string():
    tok = tokenize('')
    assert tok.text == ''
    assert tok.vault == {}
    assert detokenize(tok.text, tok.vault) == ''
