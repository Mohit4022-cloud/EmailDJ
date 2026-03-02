import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildPresetBatchSliderOverrides,
  buildPresetPreviewBatchPayload,
  mapGlobalSlidersToBatch,
  normalizePreviewContext,
} from '../src/components/presetPreviewUtils.js';

test('mapGlobalSlidersToBatch remaps UI axes to generator axes', () => {
  const mapped = mapGlobalSlidersToBatch({
    formality: 70,
    orientation: 25,
    length: 80,
    assertiveness: 10,
  });
  assert.deepEqual(mapped, {
    formality: 30,
    brevity: 20,
    directness: 90,
    personalization: 80,
  });
});

test('buildPresetBatchSliderOverrides maps preset semantics correctly', () => {
  const overrides = buildPresetBatchSliderOverrides({
    sliders: {
      formal: 80,
      outcome: 30,
      long: 25,
      diplomatic: 15,
    },
  });

  assert.deepEqual(overrides, {
    formality: 80,
    brevity: 75,
    directness: 85,
    personalization: 30,
  });
});

test('buildPresetPreviewBatchPayload composes extractor+generator input contract', () => {
  const context = normalizePreviewContext({
    prospect: {
      name: 'Alex Doe',
      title: 'SDR Manager',
      company: 'Acme',
      linkedin_url: 'https://linkedin.com/in/alex-doe',
    },
    research_text: 'Acme is scaling outbound programs in enterprise accounts this quarter.',
    company_context: {
      company_name: 'EmailDJ',
      company_url: 'https://emaildj.ai',
      current_product: 'Remix Studio',
      cta_offer_lock: 'Open to a quick chat to see if this is relevant?',
      cta_type: 'event_invite',
      other_products: 'Prospect Enrichment\nSequence QA',
      company_notes: 'We help SDR teams improve reply quality with controllable personalization.',
    },
    global_slider_state: {
      formality: 45,
      orientation: 60,
      length: 35,
      assertiveness: 25,
    },
  });

  const payload = buildPresetPreviewBatchPayload(context, [
    {
      id: 4,
      name: 'The Challenger',
      sliders: { formal: 40, outcome: 0, long: 40, diplomatic: 0 },
    },
  ]);

  assert.equal(payload.prospect.name, 'Alex Doe');
  assert.equal(payload.prospect.company_url, 'https://emaildj.ai');
  assert.equal(payload.product_context.product_name, 'Remix Studio');
  assert.equal(payload.product_context.target_outcome, '15-minute meeting');
  assert.equal(payload.offer_lock, 'Remix Studio');
  assert.equal(payload.cta_lock, 'Open to a quick chat to see if this is relevant?');
  assert.equal(payload.cta_lock_text, 'Open to a quick chat to see if this is relevant?');
  assert.equal(payload.cta_type, 'event_invite');
  assert.equal(payload.prospect_first_name, 'Alex');
  assert.equal(payload.raw_research.deep_research_paste, context.research_text);
  assert.equal(payload.presets.length, 1);
  assert.equal(payload.presets[0].preset_id, '4');
  assert.deepEqual(payload.presets[0].slider_overrides, {
    formality: 40,
    brevity: 60,
    directness: 100,
    personalization: 0,
  });
});

test('buildPresetPreviewBatchPayload leaves CTA lock empty when no lock override is provided', () => {
  const context = normalizePreviewContext({
    prospect: {
      name: 'Alex Doe',
      title: 'SDR Manager',
      company: 'Acme',
    },
    research_text: 'Acme is scaling outbound programs in enterprise accounts this quarter.',
    company_context: {
      company_name: 'EmailDJ',
      current_product: 'Remix Studio',
    },
    global_slider_state: {
      formality: 50,
      orientation: 50,
      length: 50,
      assertiveness: 50,
    },
  });

  const payload = buildPresetPreviewBatchPayload(context, [{ id: 1, name: 'Default' }]);
  assert.equal(payload.cta_lock, null);
  assert.equal(payload.cta_lock_text, null);
});
