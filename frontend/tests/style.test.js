import test from 'node:test';
import assert from 'node:assert/strict';

import { sliderToAxis, styleKey, styleToPayload } from '../src/style.js';

test('sliderToAxis maps 0..100 to -1..1', () => {
  assert.equal(sliderToAxis(0), -1);
  assert.equal(sliderToAxis(50), 0);
  assert.equal(sliderToAxis(100), 1);
});

test('style payload serialization includes four axes', () => {
  const payload = styleToPayload({ formality: 0, orientation: 100, length: 25, assertiveness: 75 });
  assert.deepEqual(payload, {
    formality: -1,
    orientation: 1,
    length: -0.5,
    assertiveness: 0.5,
  });
  assert.equal(styleKey(payload), 'f:-1|o:1|l:-0.5|a:0.5');
});
