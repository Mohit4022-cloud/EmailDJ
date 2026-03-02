import test from 'node:test';
import assert from 'node:assert/strict';

import { presetToSliderState } from '../src/components/SDRPresetLibrary.js';
import { SDR_PRESETS } from '../src/data/sdrPresets.js';

test('presetToSliderState maps preset semantics onto slider board axes', () => {
  const first = presetToSliderState(SDR_PRESETS[0]);
  assert.deepEqual(first, {
    formality: 40,
    orientation: 50,
    length: 40,
    assertiveness: 40,
  });

  const third = presetToSliderState(SDR_PRESETS[2]);
  assert.deepEqual(third, {
    formality: 80,
    orientation: 40,
    length: 30,
    assertiveness: 100,
  });
});

test('presetToSliderState clamps invalid slider values safely', () => {
  const mapped = presetToSliderState({
    sliders: {
      formal: 300,
      outcome: -20,
      long: '70',
      diplomatic: undefined,
    },
  });
  assert.deepEqual(mapped, {
    formality: 0,
    orientation: 0,
    length: 70,
    assertiveness: 50,
  });
});

