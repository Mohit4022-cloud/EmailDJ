import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { inspectReleaseConfig } from '../scripts/check-release-config.mjs';

function makeDist({ hubUrl = 'https://hub.example.com', previewPipeline = 'off' } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'emaildj-web-release-'));
  const dist = path.join(root, 'dist');
  const assets = path.join(dist, 'assets');
  const envEntries = ['BASE_URL:"/"'];
  if (hubUrl !== null) envEntries.push(`VITE_HUB_URL:${JSON.stringify(hubUrl)}`);
  if (previewPipeline !== null) {
    envEntries.push(`VITE_PRESET_PREVIEW_PIPELINE:${JSON.stringify(previewPipeline)}`);
  }
  fs.mkdirSync(assets, { recursive: true });
  fs.writeFileSync(
    path.join(dist, 'index.html'),
    '<!doctype html><html><head><script type="module" src="/assets/index.js"></script></head><body></body></html>',
    'utf8',
  );
  fs.writeFileSync(
    path.join(assets, 'index.js'),
    `const ENV={${envEntries.join(',')}}; function incidentalText(){ return "function buttons stay on screen"; }`,
    'utf8',
  );
  return dist;
}

test('release config accepts deployed hub URL and explicit preview flag', () => {
  const dist = makeDist();

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://hub.example.com',
    expectedPreviewPipeline: 'off',
  });

  assert.equal(result.ok, true);
  assert.deepEqual(result.failures, []);
});

test('release config rejects missing deployed hub URL', () => {
  const dist = makeDist();

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: '',
    expectedPreviewPipeline: 'off',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_missing'));
});

test('release config rejects local hub URL and missing preview flag', () => {
  const dist = makeDist({ hubUrl: 'http://127.0.0.1:8000', previewPipeline: '' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'http://127.0.0.1:8000',
    expectedPreviewPipeline: '',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_not_deployed_https'));
  assert.ok(result.failures.includes('expected_preview_pipeline_missing'));
});

test('release config rejects deployed hub URL with path or query', () => {
  const dist = makeDist({ hubUrl: 'https://hub.example.com/web/v1?debug=1' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://hub.example.com/web/v1?debug=1',
    expectedPreviewPipeline: 'off',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_not_root'));
});

test('release config rejects stale dist bundle that lacks expected values', () => {
  const dist = makeDist({ hubUrl: 'https://old-hub.example.com', previewPipeline: 'on' });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://new-hub.example.com',
    expectedPreviewPipeline: 'off',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_hub_url_not_found_in_dist'));
  assert.ok(result.failures.includes('expected_preview_pipeline_not_found_in_dist'));
});

test('release config rejects incidental preview text without the Vite env literal', () => {
  const dist = makeDist({ hubUrl: 'https://hub.example.com', previewPipeline: null });

  const result = inspectReleaseConfig({
    distDir: dist,
    expectedHubUrl: 'https://hub.example.com',
    expectedPreviewPipeline: 'on',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.includes('expected_preview_pipeline_not_found_in_dist'));
});
