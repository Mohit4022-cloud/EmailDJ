import asyncio
import json

from starlette.requests import Request
from starlette.responses import StreamingResponse

from api.middleware.pii_redaction import PiiRedactionMiddleware
from email_generation.streaming import _event_generator, _eventsource_stream
from pii.presidio_redactor import _replace_entities
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


def test_presidio_person_tokens_restore_first_name_only():
    class Entity:
        entity_type = "PERSON"
        start = 0
        end = len("Alex Karp")
        score = 1.0

    redacted, vault = _replace_entities("Alex Karp", [Entity()])
    assert redacted.startswith("[PERSON_")
    assert detokenize(redacted, vault) == "Alex"


def test_eventsource_stream_serializes_json_data():
    async def collect():
        async def gen():
            yield 'hello'

        items = []
        async for item in _eventsource_stream('req-2', gen()):
            items.append(item)
        return items

    items = asyncio.run(collect())
    token = next(item for item in items if item['event'] == 'token')
    payload = json.loads(token['data'])
    assert payload['request_id'] == 'req-2'
    assert payload['token'] == 'hello'


def test_event_generator_supports_structured_chunk_payload():
    async def collect():
        async def gen():
            yield {"token": "Hel", "chunk_index": 0, "chunk_len": 3, "chunk_mode": "stable_chars"}
            yield {"token": "lo", "chunk_index": 1, "chunk_len": 2, "chunk_mode": "stable_chars"}

        items = []
        async for item in _event_generator(
            'req-3',
            gen(),
            done_extra={"stream_checksum": "abc123", "total_chunks": 2},
            event_extra={"generation_id": "gen-3", "draft_id": 12},
        ):
            items.append(item)
        return items

    items = asyncio.run(collect())
    start = next(item for item in items if item["event"] == "start")
    assert start["data"]["generation_id"] == "gen-3"
    assert start["data"]["draft_id"] == 12
    tokens = [item for item in items if item["event"] == "token"]
    assert len(tokens) == 2
    assert tokens[0]["data"]["token"] == "Hel"
    assert tokens[0]["data"]["chunk_index"] == 0
    assert tokens[0]["data"]["generation_id"] == "gen-3"
    assert tokens[0]["data"]["draft_id"] == 12
    assert tokens[1]["data"]["token"] == "lo"
    assert tokens[1]["data"]["chunk_index"] == 1

    done = next(item for item in items if item["event"] == "done")
    assert done["data"]["stream_checksum"] == "abc123"
    assert done["data"]["total_chunks"] == 2
    assert done["data"]["generation_id"] == "gen-3"
    assert done["data"]["draft_id"] == 12


def test_event_generator_detokenizes_sse_payloads():
    async def collect():
        async def gen():
            yield {"token": "Hi [PERSON_TEST], "}

        items = []
        async for item in _event_generator(
            "req-4",
            gen(),
            done_extra={"final": {"body": "Hi [PERSON_TEST], ready."}},
            token_vault={"[PERSON_TEST]": "Alex"},
        ):
            items.append(item)
        return items

    items = asyncio.run(collect())
    token = next(item for item in items if item["event"] == "token")
    assert token["data"]["token"] == "Hi Alex, "
    done = next(item for item in items if item["event"] == "done")
    assert done["data"]["final"]["body"] == "Hi Alex, ready."


def test_pii_middleware_detokenizes_streaming_json_response():
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def call_next(request):
        request.state.token_vault["[PERSON_TEST]"] = "Alex"

        async def body():
            yield b'{"combined":"Hi [PERSON_TEST], ready."}'

        return StreamingResponse(body(), media_type="application/json")

    async def run():
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []}, receive)
        middleware = PiiRedactionMiddleware(app=lambda scope, receive, send: None)
        return await middleware.dispatch(request, call_next)

    response = asyncio.run(run())
    payload = json.loads(response.body.decode("utf-8"))
    assert payload["combined"] == "Hi Alex, ready."
