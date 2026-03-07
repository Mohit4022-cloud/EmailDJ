from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from scripts.debug_run_harness import _extract_stream


def test_extract_stream_parses_tokens_and_done_payload():
    stream_text = (
        'event: token\n'
        'data: {"token":"Hel","sequence":1}\n\n'
        'event: token\n'
        'data: {"token":"lo","sequence":2}\n\n'
        'event: done\n'
        'data: {"stream_checksum":"abc","total_chunks":2}\n\n'
    )
    rendered, done = _extract_stream(stream_text)

    assert rendered == "Hello"
    assert done["stream_checksum"] == "abc"
    assert done["total_chunks"] == 2


def test_extract_stream_ignores_non_token_events():
    stream_text = (
        'event: start\n'
        'data: {"request_id":"r1"}\n\n'
        'event: done\n'
        'data: {"ok":true}\n\n'
    )
    rendered, done = _extract_stream(stream_text)
    assert rendered == ""
    assert done == {"ok": True}
