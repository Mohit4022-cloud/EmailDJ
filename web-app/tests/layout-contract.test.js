import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const mainSource = readFileSync(resolve(__dirname, '../src/main.js'), 'utf8');

test('draft workspace renders before brief inputs while preserving control mounts', () => {
  const workspaceIndex = mainSource.indexOf('id="workspacePanel"');
  const inputIndex = mainSource.indexOf('id="inputPanel"');

  assert.ok(workspaceIndex > -1, 'workspace panel mount is missing');
  assert.ok(inputIndex > -1, 'input panel mount is missing');
  assert.ok(workspaceIndex < inputIndex, 'draft workspace should be the primary panel');

  const workspaceCommandIndex = mainSource.indexOf('id="workspaceCommandStrip"');
  const editorIndex = mainSource.indexOf('id="editorMount"');

  assert.ok(workspaceCommandIndex > -1, 'workspace command strip is missing');
  assert.ok(editorIndex > -1, 'editor mount is missing');
  assert.ok(workspaceCommandIndex < editorIndex, 'workspace command strip should sit above the draft editor');

  for (const id of [
    'editorMount',
    'sliderBoard',
    'statusLine',
    'generateBtn',
    'workspaceGenerateBtn',
    'workspaceProspectChip',
    'workspaceOfferChip',
    'workspaceResearchChip',
    'saveRemixBtn',
    'presetLibraryMount',
  ]) {
    assert.ok(mainSource.includes(`id="${id}"`), `${id} mount is missing`);
  }
});
