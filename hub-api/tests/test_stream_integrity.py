from __future__ import annotations

import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))


async def _collect_lossless_tokens(text: str) -> tuple[str, dict]:
    from api.routes.web_mvp import _token_stream

    mode_info: dict = {}
    parts: list[str] = []
    async for payload in _token_stream(text, mode_info):
        if isinstance(payload, dict):
            parts.append(str(payload.get("token") or ""))
        else:
            parts.append(str(payload))
    return "".join(parts), mode_info


def test_lossless_stream_chunks_reconstruct_with_checksum(monkeypatch):
    from api.routes.web_mvp import _sha256_hex

    monkeypatch.setenv("FEATURE_LOSSLESS_STREAMING", "1")
    monkeypatch.setenv("EMAILDJ_WEB_MVP_STREAM_CHUNK_SIZE", "7")
    text = "Subject: Remix Studio\nBody:\nHi Alex, complete deterministic stream content."

    rendered, mode_info = asyncio.run(_collect_lossless_tokens(text))

    assert rendered == text
    assert mode_info["stream_chunk_mode"] == "stable_chars"
    assert mode_info["total_chars"] == len(text)
    assert mode_info["total_chunks"] >= 1
    assert mode_info["stream_missing_chunks"] == 0
    assert mode_info["stream_checksum"] == _sha256_hex(rendered)
