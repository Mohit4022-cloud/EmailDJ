import test from 'node:test';
import assert from 'node:assert/strict';

import { generatePresetPreviewsBatch } from '../src/api/client.js';

test('generatePresetPreviewsBatch returns parsed JSON on success', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ previews: [{ preset_id: '1' }], meta: { request_id: 'r1' } }),
  });

  try {
    const result = await generatePresetPreviewsBatch({ presets: [] }, { timeoutMs: 100 });
    assert.equal(Array.isArray(result.previews), true);
    assert.equal(result.meta.request_id, 'r1');
  } finally {
    global.fetch = originalFetch;
  }
});

test('generatePresetPreviewsBatch includes backend error detail on failure', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: false,
    status: 503,
    json: async () => ({ detail: { error: 'preview_pipeline_disabled' } }),
  });

  try {
    await assert.rejects(
      () => generatePresetPreviewsBatch({ presets: [] }, { timeoutMs: 100 }),
      /preview_pipeline_disabled/
    );
  } finally {
    global.fetch = originalFetch;
  }
});

test('generatePresetPreviewsBatch times out and surfaces a clear error', async () => {
  const originalFetch = global.fetch;
  global.fetch = (_url, options = {}) =>
    new Promise((_resolve, reject) => {
      options.signal?.addEventListener('abort', () => {
        const error = new Error('aborted');
        error.name = 'AbortError';
        reject(error);
      });
    });

  try {
    await assert.rejects(
      () => generatePresetPreviewsBatch({ presets: [] }, { timeoutMs: 10 }),
      /timed out/
    );
  } finally {
    global.fetch = originalFetch;
  }
});
