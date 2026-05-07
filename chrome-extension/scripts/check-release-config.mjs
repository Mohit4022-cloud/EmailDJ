import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '0.0.0.0', '::1', '[::1]']);

function hubUrlFinding(value) {
  try {
    const url = new URL(String(value || '').trim());
    if (url.protocol !== 'https:') return 'expected_hub_url_not_deployed_https';
    if (LOCAL_HOSTS.has(url.hostname) || url.hostname.endsWith('.local')) {
      return 'expected_hub_url_not_deployed_https';
    }
    if (url.pathname !== '/' || url.search || url.hash || url.username || url.password) {
      return 'expected_hub_url_not_root';
    }
    return null;
  } catch {
    return 'expected_hub_url_not_deployed_https';
  }
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function walkFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const nextPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...walkFiles(nextPath));
    } else {
      files.push(nextPath);
    }
  }
  return files;
}

function readBuiltJavaScript(distDir) {
  return walkFiles(distDir)
    .filter((filePath) => /\.(?:js|mjs)$/.test(filePath))
    .map((filePath) => fs.readFileSync(filePath, 'utf8'))
    .join('\n');
}

function expectedHubHostPermission(value) {
  const url = new URL(String(value || '').trim());
  return `${url.origin}/*`;
}

export function inspectReleaseConfig({
  distDir = path.resolve('dist'),
  expectedHubUrl = process.env.EMAILDJ_EXPECTED_HUB_URL || process.env.VITE_HUB_URL || '',
  expectedBetaKey = process.env.EMAILDJ_EXPECTED_BETA_KEY || process.env.VITE_EMAILDJ_BETA_KEY || '',
} = {}) {
  const failures = [];
  const warnings = [];
  const resolvedDistDir = path.resolve(distDir);
  const manifestPath = path.join(resolvedDistDir, 'manifest.json');

  if (!fs.existsSync(manifestPath)) {
    failures.push(`missing_dist_manifest:${manifestPath}`);
    return { ok: false, failures, warnings, distDir: resolvedDistDir, filesScanned: 0 };
  }

  const manifest = readJson(manifestPath);
  if (manifest.manifest_version !== 3) failures.push('manifest_version_not_mv3');
  if (!manifest.side_panel?.default_path) failures.push('side_panel_default_path_missing');
  if (!manifest.background?.service_worker) failures.push('background_service_worker_missing');
  if (!Array.isArray(manifest.permissions) || !manifest.permissions.includes('storage')) {
    failures.push('storage_permission_missing');
  }
  if (!Array.isArray(manifest.permissions) || !manifest.permissions.includes('sidePanel')) {
    failures.push('sidePanel_permission_missing');
  }

  const normalizedHubUrl = String(expectedHubUrl || '').trim().replace(/\/+$/, '');
  if (!normalizedHubUrl) {
    failures.push('expected_hub_url_missing');
  } else {
    const finding = hubUrlFinding(normalizedHubUrl);
    if (finding) failures.push(finding);
  }
  if (normalizedHubUrl && !failures.includes('expected_hub_url_not_deployed_https') && !failures.includes('expected_hub_url_not_root')) {
    const hostPermissions = Array.isArray(manifest.host_permissions) ? manifest.host_permissions : [];
    const expectedPermission = expectedHubHostPermission(normalizedHubUrl);
    if (!hostPermissions.includes(expectedPermission)) {
      failures.push('expected_hub_host_permission_missing');
    }
  }

  const normalizedBetaKey = String(expectedBetaKey || '').trim();
  if (!normalizedBetaKey) {
    failures.push('expected_beta_key_missing');
  } else if (normalizedBetaKey === 'dev-beta-key') {
    failures.push('expected_beta_key_is_dev');
  }

  const builtJavaScript = readBuiltJavaScript(resolvedDistDir);
  if (normalizedHubUrl && !builtJavaScript.includes(normalizedHubUrl)) {
    failures.push('expected_hub_url_not_found_in_dist');
  }
  if (normalizedBetaKey && normalizedBetaKey !== 'dev-beta-key' && !builtJavaScript.includes(normalizedBetaKey)) {
    warnings.push('expected_beta_key_not_found_in_dist_operator_override_required');
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
