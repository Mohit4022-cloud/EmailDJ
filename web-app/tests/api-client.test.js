import test from 'node:test';
import assert from 'node:assert/strict';

import { fetchRuntimeConfig, generatePresetPreviewsBatch, resolveHubUrl } from '../src/api/client.js';

test('resolveHubUrl throws when production build is missing VITE_HUB_URL', () => {
  assert.throws(
    () => resolveHubUrl({ PROD: true, VITE_HUB_URL: '' }),
    /Missing VITE_HUB_URL/
  );
});

test('resolveHubUrl keeps localhost fallback in non-production environments', () => {
  assert.equal(resolveHubUrl({ DEV: true }), 'http://127.0.0.1:8000');
});

test('resolveHubUrl trims trailing slash from configured hub URL', () => {
  assert.equal(resolveHubUrl({ PROD: true, VITE_HUB_URL: 'https://hub.example.com/' }), 'https://hub.example.com');
});

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

test('fetchRuntimeConfig returns debug payload', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ runtime_mode: 'real', provider_stub_enabled: false }),
  });
  try {
    const payload = await fetchRuntimeConfig({ endpoint: 'generate', bucketKey: 'ui' });
    assert.equal(payload.runtime_mode, 'real');
    assert.equal(payload.provider_stub_enabled, false);
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
