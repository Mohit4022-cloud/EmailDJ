import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildPreviewCacheKey,
  buildPreviewContextHash,
  normalizePreviewContext,
  resolveEffectiveSliderState,
} from '../src/components/presetPreviewUtils.js';

function baseContext() {
  return normalizePreviewContext({
    prospect: {
      name: 'Alex Karp',
      title: 'CEO',
      company: 'Palantir',
      linkedin_url: 'https://linkedin.com/in/alex-karp',
    },
    research_text:
      'Palantir is scaling enterprise AI initiatives through AIP with executive focus on measurable outcomes.',
    company_context: {
      company_name: 'EmailDJ',
      company_url: 'https://emaildj.ai',
      current_product: 'Remix Studio',
      other_products: 'Prospect Enrichment\nSequence QA',
      company_notes: 'We help SDR teams improve reply quality with controlled personalization.',
    },
    global_slider_state: {
      formality: 48,
      orientation: 62,
      length: 41,
      assertiveness: 37,
    },
  });
}

test('buildPreviewContextHash is stable for equivalent normalized context', () => {
  const first = baseContext();
  const second = baseContext();
  assert.equal(buildPreviewContextHash(first), buildPreviewContextHash(second));
});

test('buildPreviewContextHash changes when deep research or sliders change', () => {
  const first = baseContext();
  const second = baseContext();
  second.research_text = `${second.research_text} Added new trigger.`;

  const third = baseContext();
  third.global_slider_state.orientation = 20;

  assert.notEqual(buildPreviewContextHash(first), buildPreviewContextHash(second));
  assert.notEqual(buildPreviewContextHash(first), buildPreviewContextHash(third));
});

test('buildPreviewCacheKey isolates preview entries by preset id', () => {
  const hash = buildPreviewContextHash(baseContext());
  assert.notEqual(buildPreviewCacheKey(hash, 1), buildPreviewCacheKey(hash, 2));
});

test('resolveEffectiveSliderState applies preset slider overrides over globals', () => {
  const effective = resolveEffectiveSliderState(
    {
      formality: 55,
      orientation: 55,
      length: 55,
      assertiveness: 55,
    },
    {
      sliders: {
        formal: 80,
        outcome: 10,
        long: 25,
        diplomatic: 15,
      },
    }
  );

  assert.deepEqual(effective, {
    formality: 20,
    orientation: 10,
    length: 25,
    assertiveness: 15,
  });
});

