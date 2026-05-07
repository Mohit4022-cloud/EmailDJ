import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { inspectReleaseConfig } from '../scripts/check-release-config.mjs';

function makeDist({ hubUrl = 'https://hub.example.com', betaKey = 'ops-key' } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'emaildj-extension-release-'));
  const dist = path.join(root, 'dist');
  const assets = path.join(dist, 'assets');
  fs.mkdirSync(assets, { recursive: true });
  fs.writeFileSync(
    path.join(dist, 'manifest.json'),
    JSON.stringify({
      manifest_version: 3,
      permissions: ['storage', 'sidePanel'],
      background: { service_worker: 'service-worker-loader.js' },
      side_panel: { default_path: 'src/side-panel/index.html' },
    }),
    'utf8',
  );
  fs.writeFileSync(
    path.join(assets, 'index.js'),
    `const HUB_URL=${JSON.stringify(hubUrl)}; const BETA_KEY=${JSON.stringify(betaKey)};`,
    'utf8',
  );
  return dist;
}

test('release config accepts deployed hub URL and non-dev beta key', () => {
  const dist = makeDist();

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://hub.example.com',
    expectedBetaKey: 'ops-key',
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.failures, []);
});

test('release config rejects missing deployed hub URL', () => {
  const dist = makeDist();

  const result = inspectReleaseConfig({ distDir: dist, expectedHubUrl: '' });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_missing'));
});

test('release config rejects local hub URL and dev beta key', () => {
  const dist = makeDist({ hubUrl: 'http://127.0.0.1:8000', betaKey: 'dev-beta-key' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'http://127.0.0.1:8000',
    expectedBetaKey: 'dev-beta-key',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_not_deployed_https'));
  assert.ok(result.failures.includes('expected_beta_key_is_dev'));
});

test('release config rejects deployed hub URL with path or query', () => {
  const dist = makeDist({ hubUrl: 'https://hub.example.com/web/v1?debug=1' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://hub.example.com/web/v1?debug=1',
    expectedBetaKey: 'ops-key',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_not_root'));
});

test('release config rejects missing beta key', () => {
  const dist = makeDist({ betaKey: '' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://hub.example.com',
    expectedBetaKey: '',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_beta_key_missing'));
});

test('release config rejects stale dist bundle that lacks expected hub URL', () => {
  const dist = makeDist({ hubUrl: 'https://old-hub.example.com' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://new-hub.example.com',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_not_found_in_dist'));
});
