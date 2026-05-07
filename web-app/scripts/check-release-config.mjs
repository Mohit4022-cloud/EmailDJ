import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]']);
const PREVIEW_VALUES = new Set(['on', 'off', 'true', 'false', '1', '0']);
const LOCAL_HUB_URLS = [
  'http://127.0.0.1:8000',
  'http://localhost:8000',
  'http://0.0.0.0:8000',
  'http://[::1]:8000',
];

function compactValueCandidates(...values) {
  return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))];
}

function isSafeHttpsUrl(value) {
  try {
    const url = new URL(String(value || '').trim());
    return url.protocol === 'https:' && !LOCAL_HOSTS.has(url.hostname);
  } catch {
    return false;
  }
}

function walkFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const nextPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(nextPath));
    } else {
      files.push(nextPath);
    }
  }
  return files;
}

function readBuiltText(distDir) {
  return walkFiles(distDir)
    .filter((filePath) => /\.(?:html|js|mjs|css)$/.test(filePath))
    .map((filePath) => fs.readFileSync(filePath, 'utf8'))
    .join('\n');
}

function hasViteEnvLiteral(builtText, key, expectedValues) {
  return expectedValues.some((value) => {
    const serialized = JSON.stringify(value);
    return builtText.includes(`${key}:${serialized}`) || builtText.includes(`${JSON.stringify(key)}:${serialized}`);
  });
}

export function inspectReleaseConfig({
  distDir = path.resolve('dist'),
  expectedHubUrl = process.env.EMAILDJ_EXPECTED_HUB_URL || process.env.VITE_HUB_URL || '',
  expectedPreviewPipeline = process.env.EMAILDJ_EXPECTED_PRESET_PREVIEW_PIPELINE || process.env.VITE_PRESET_PREVIEW_PIPELINE || '',
} = {}) {
  const failures = [];
  const warnings = [];
  const resolvedDistDir = path.resolve(distDir);
  const indexPath = path.join(resolvedDistDir, 'index.html');

  if (!fs.existsSync(indexPath)) {
    failures.push(`missing_dist_index:${indexPath}`);
    return { ok: false, failures, warnings, distDir: resolvedDistDir, filesScanned: 0 };
  }

  const rawHubUrl = String(expectedHubUrl || '').trim();
  const normalizedHubUrl = rawHubUrl.replace(/\/+$/, '');
  if (!normalizedHubUrl) {
    failures.push('expected_hub_url_missing');
  } else if (!isSafeHttpsUrl(normalizedHubUrl)) {
    failures.push('expected_hub_url_not_deployed_https');
  }

  const rawPreview = String(expectedPreviewPipeline || '').trim();
  const normalizedPreview = rawPreview.toLowerCase();
  if (!normalizedPreview) {
    failures.push('expected_preview_pipeline_missing');
  } else if (!PREVIEW_VALUES.has(normalizedPreview)) {
    failures.push('expected_preview_pipeline_invalid');
  }

  const builtText = readBuiltText(resolvedDistDir);
  if (
    normalizedHubUrl &&
    !hasViteEnvLiteral(builtText, 'VITE_HUB_URL', compactValueCandidates(rawHubUrl, normalizedHubUrl))
  ) {
    failures.push('expected_hub_url_not_found_in_dist');
  }
  if (
    normalizedPreview &&
    !hasViteEnvLiteral(
      builtText,
      'VITE_PRESET_PREVIEW_PIPELINE',
      compactValueCandidates(rawPreview, normalizedPreview),
    )
  ) {
    failures.push('expected_preview_pipeline_not_found_in_dist');
  }
  if (hasViteEnvLiteral(builtText, 'VITE_HUB_URL', LOCAL_HUB_URLS)) {
    warnings.push('local_dev_hub_url_string_present_in_dist');
  }

  return {
    ok: failures.length === 0,
    failures,
    warnings,
    distDir: resolvedDistDir,
    filesScanned: walkFiles(resolvedDistDir).length,
  };
}

function main() {
  const result = inspectReleaseConfig();
  console.log(JSON.stringify(result, null, 2));
  return result.ok ? 0 : 1;
}

const executedUrl = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : '';

if (import.meta.url === executedUrl) {
  process.exitCode = main();
}
