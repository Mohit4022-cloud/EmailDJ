import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildHubHeaders,
  normalizeHubUrl,
  resolveHubConfigFromValues,
  saveHubConfig,
} from '../src/side-panel/hub-client.js';

test('normalizeHubUrl trims trailing slashes and preserves valid http origins', () => {
  assert.equal(normalizeHubUrl('https://hub.example.com///'), 'https://hub.example.com');
  assert.equal(normalizeHubUrl('http://127.0.0.1:8000/'), 'http://127.0.0.1:8000');
});

test('normalizeHubUrl rejects unsupported or malformed values', () => {
  assert.equal(normalizeHubUrl('chrome-extension://abc'), 'http://127.0.0.1:8000');
  assert.equal(normalizeHubUrl('not a url'), 'http://127.0.0.1:8000');
});

test('resolveHubConfigFromValues prefers stored operator config over build defaults', () => {
  const config = resolveHubConfigFromValues({
    env: {
      VITE_HUB_URL: 'https://build-hub.example.com',
      VITE_EMAILDJ_BETA_KEY: 'build-key',
    },
    storedHubUrl: 'https://runtime-hub.example.com/',
    storedBetaKey: 'runtime-key',
  });

  assert.deepEqual(config, {
    hubUrl: 'https://runtime-hub.example.com',
    betaKey: 'runtime-key',
  });
});

test('resolveHubConfigFromValues fails closed in production when hub URL is missing', () => {
  assert.throws(
    () => resolveHubConfigFromValues({ env: { PROD: true } }),
    /Missing VITE_HUB_URL/,
  );
});

test('resolveHubConfigFromValues rejects localhost hub URLs in production', () => {
  assert.throws(
    () => resolveHubConfigFromValues({ env: { PROD: true, VITE_HUB_URL: 'http://127.0.0.1:8000' } }),
    /deployed https:\/\/ hub-api origin/,
  );
});

test('resolveHubConfigFromValues rejects dev beta key in production', () => {
  assert.throws(
    () => resolveHubConfigFromValues({
      env: {
        PROD: true,
        VITE_HUB_URL: 'https://hub.example.com',
        VITE_EMAILDJ_BETA_KEY: 'dev-beta-key',
      },
    }),
    /cannot be dev-beta-key/,
  );
});

test('resolveHubConfigFromValues allows production operator override without build-time hub URL', () => {
  const config = resolveHubConfigFromValues({
    env: { PROD: true },
    storedHubUrl: 'https://runtime-hub.example.com/',
    storedBetaKey: 'runtime-key',
  });

  assert.deepEqual(config, {
    hubUrl: 'https://runtime-hub.example.com',
    betaKey: 'runtime-key',
  });
});

test('buildHubHeaders adds beta key without dropping caller headers', () => {
  assert.deepEqual(
    buildHubHeaders({ betaKey: 'ops-key' }, { 'Content-Type': 'application/json' }),
    {
      'Content-Type': 'application/json',
      'X-EmailDJ-Beta-Key': 'ops-key',
    },
  );
});

test('saveHubConfig persists normalized operator config to chrome storage', async () => {
  const stored = {};
  globalThis.chrome = {
    storage: {
      sync: {
        async set(values) {
          Object.assign(stored, values);
        },
      },
    },
  };

  try {
    const config = await saveHubConfig({
      hubUrl: 'https://runtime-hub.example.com///',
      betaKey: ' runtime-key ',
    });

    assert.deepEqual(config, {
      hubUrl: 'https://runtime-hub.example.com',
      betaKey: 'runtime-key',
    });
    assert.deepEqual(stored, {
      emaildjHubUrl: 'https://runtime-hub.example.com',
      emaildjBetaKey: 'runtime-key',
    });
  } finally {
    delete globalThis.chrome;
  }
});
