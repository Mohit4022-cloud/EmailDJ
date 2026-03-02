import test from 'node:test';
import assert from 'node:assert/strict';

import { buildPresetMetaHtml, presetToSliderState } from '../src/components/SDRPresetLibrary.js';
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

test('preset meta panel keeps The Vibe, Why it works, and Slider Settings in one ordered block', () => {
  const html = buildPresetMetaHtml({
    vibeLabel: 'The Challenger',
    vibeTags: ['Bold', 'Problem-Led', 'Short-Form'],
    whyItWorks: ['Creates urgency around a hidden cost.', 'Reframes inaction as business risk.'],
    sliderSummary: {
      formality: 30,
      orientation: 10,
      length: 35,
      assertiveness: 15,
    },
  });

  const vibeIndex = html.indexOf('The Vibe');
  const whyIndex = html.indexOf('Why it works');
  const sliderIndex = html.indexOf('Slider Settings');

  assert.ok(vibeIndex >= 0);
  assert.ok(whyIndex >= 0);
  assert.ok(sliderIndex >= 0);
  assert.ok(vibeIndex < whyIndex);
  assert.ok(whyIndex < sliderIndex);
});
