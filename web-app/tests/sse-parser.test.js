import test from 'node:test';
import assert from 'node:assert/strict';

import { parseSseBlock } from '../src/api/client.js';

test('parseSseBlock parses event and JSON payload', () => {
  const message = 'event: token\ndata: {"token":"Hello"}\n\n';
  const out = parseSseBlock(message.trim());
  assert.equal(out.event, 'token');
  assert.equal(out.data.token, 'Hello');
});
