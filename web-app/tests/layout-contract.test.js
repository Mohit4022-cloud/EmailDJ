import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const indexSource = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
const mainSource = readFileSync(resolve(__dirname, '../src/main.js'), 'utf8');
const editorSource = readFileSync(resolve(__dirname, '../src/components/EmailEditor.js'), 'utf8');

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

test('draft editor owns the primary canvas chrome and empty state', () => {
  const toolbarIndex = editorSource.indexOf('class="editor-toolbar"');
  const bodyIndex = editorSource.indexOf('id="emailBody"');
  const metaIndex = editorSource.indexOf('id="draftMeta"');

  assert.ok(editorSource.includes('id="editorFrame"'), 'editor frame is missing');
  assert.ok(editorSource.includes('id="draftCanvasTitle"'), 'draft canvas title is missing');
  assert.ok(editorSource.includes('data-placeholder="Draft will stream here'), 'editor empty state placeholder is missing');
  assert.ok(toolbarIndex > -1, 'editor toolbar is missing');
  assert.ok(bodyIndex > -1, 'email body mount is missing');
  assert.ok(metaIndex > -1, 'draft meta mount is missing');
  assert.ok(toolbarIndex < bodyIndex, 'editor toolbar should sit above the draft canvas');
  assert.ok(bodyIndex < metaIndex, 'draft meta should sit below the draft canvas');
});

test('mobile workspace controls stay within the viewport grid', () => {
  assert.ok(indexSource.includes('@media (max-width: 760px)'), 'mobile layout contract is missing');
  assert.ok(
    indexSource.includes('.workspace-heading {\n          display: grid;\n          grid-template-columns: minmax(0, 1fr);'),
    'mobile workspace heading should use one constrained grid track',
  );
  assert.ok(
    indexSource.includes('.workspace-actions > button {\n          width: 100%;'),
    'mobile workspace action buttons should fill their available row',
  );
  assert.ok(
    indexSource.includes('.editor-toolbar > div {\n        min-width: 0;'),
    'editor toolbar text column should be shrinkable on narrow screens',
  );
});
