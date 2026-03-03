import test from 'node:test';
import assert from 'node:assert/strict';

import { consumeStream, parseSseBlock } from '../src/api/client.js';

test('parseSseBlock parses event and JSON payload', () => {
  const message = 'event: token\ndata: {"token":"Hello"}\n\n';
  const out = parseSseBlock(message.trim());
  assert.equal(out.event, 'token');
  assert.equal(out.data.token, 'Hello');
});

test('parseSseBlock parses legacy python-dict payload', () => {
  const message = "event: token\ndata: {'request_id': 'abc', 'sequence': 1, 'token': 'Hello'}\n\n";
  const out = parseSseBlock(message.trim());
  assert.equal(out.event, 'token');
  assert.equal(out.data.request_id, 'abc');
  assert.equal(out.data.sequence, 1);
  assert.equal(out.data.token, 'Hello');
});

test('consumeStream handles CRLF-delimited SSE blocks', async () => {
  const originalFetch = globalThis.fetch;
  const encoder = new TextEncoder();
  const chunks = [
    'event: token\r\ndata: {"token":"Hel"}\r\n\r\n',
    'event: token\r\ndata: {"token":"lo"}\r\n\r\nevent: done\r\ndata: {"ok":true}\r\n\r\n',
  ];

  globalThis.fetch = async () => ({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
  });

  try {
    const tokens = [];
    await consumeStream('req-1', (msg) => {
      if (msg.event === 'token') tokens.push(msg.data.token);
    });
    assert.equal(tokens.join(''), 'Hello');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('consumeStream forwards structured chunk metadata', async () => {
  const originalFetch = globalThis.fetch;
  const encoder = new TextEncoder();
  const chunks = [
    'event: token\r\ndata: {"token":"Hel","sequence":1,"chunk_index":0,"chunk_len":3}\r\n\r\n',
    'event: token\r\ndata: {"token":"lo","sequence":2,"chunk_index":1,"chunk_len":2}\r\n\r\n',
    'event: done\r\ndata: {"stream_checksum":"abc","total_chunks":2}\r\n\r\n',
  ];

  globalThis.fetch = async () => ({
    ok: true,
    body: new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
  });

  try {
    const seen = [];
    await consumeStream('req-2', (msg) => {
      if (msg.event === 'token') {
        seen.push(`${msg.data.chunk_index}:${msg.data.token}`);
      }
    });
    assert.deepEqual(seen, ['0:Hel', '1:lo']);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
