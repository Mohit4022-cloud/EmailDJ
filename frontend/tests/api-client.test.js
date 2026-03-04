import test from 'node:test';
import assert from 'node:assert/strict';

import {
  fetchPresetPreview,
  fetchRuntimeConfig,
  startProspectEnrichment,
  startTargetEnrichment,
} from '../src/api/client.js';

test('fetchPresetPreview returns parsed JSON on success', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ preset_id: '1', subject: 'Subject', body: 'Body' }),
  });

  try {
    const result = await fetchPresetPreview({ preset_id: '1' });
    assert.equal(result.preset_id, '1');
    assert.equal(result.subject, 'Subject');
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
    const payload = await fetchRuntimeConfig();
    assert.equal(payload.runtime_mode, 'real');
    assert.equal(payload.provider_stub_enabled, false);
  } finally {
    global.fetch = originalFetch;
  }
});

test('target enrichment starter surfaces detail on failure', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: false,
    status: 422,
    json: async () => ({ detail: { error: 'company_name_or_url_required' } }),
  });

  try {
    await assert.rejects(
      () => startTargetEnrichment({}),
      /company_name_or_url_required/
    );
  } finally {
    global.fetch = originalFetch;
  }
});

test('prospect enrichment starter returns accepted payload', async () => {
  const originalFetch = global.fetch;
  global.fetch = async () => ({
    ok: true,
    json: async () => ({ request_id: 'r1', stream_url: '/web/v1/stream/r1' }),
  });

  try {
    const result = await startProspectEnrichment({ prospect_name: 'Alex', target_company_name: 'Acme' });
    assert.equal(result.request_id, 'r1');
    assert.equal(result.stream_url, '/web/v1/stream/r1');
  } finally {
    global.fetch = originalFetch;
  }
});
