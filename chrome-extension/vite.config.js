import { defineConfig } from 'vite';
import { crx } from '@crxjs/vite-plugin';
import manifest from './manifest.json';

function hubHostPermission() {
  const rawUrl = String(process.env.VITE_HUB_URL || process.env.EMAILDJ_EXPECTED_HUB_URL || '').trim();
  if (!rawUrl) return null;
  try {
    const url = new URL(rawUrl);
    if (url.protocol !== 'https:') return null;
    return `${url.origin}/*`;
  } catch {
    return null;
  }
}

function releaseManifest() {
  const permission = hubHostPermission();
  if (!permission) return manifest;
  return {
    ...manifest,
    host_permissions: [...new Set([...(manifest.host_permissions || []), permission])],
  };
}

export default defineConfig({
  plugins: [
    crx({ manifest: releaseManifest() }),
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
});
