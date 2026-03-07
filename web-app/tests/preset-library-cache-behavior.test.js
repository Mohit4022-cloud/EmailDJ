import test from 'node:test';
import assert from 'node:assert/strict';

import { SDRPresetLibrary } from '../src/components/SDRPresetLibrary.js';

function makeContext() {
  return {
    prospect: {
      name: 'Rohan Singh',
      title: 'VP Revenue Operations',
      company: 'Acme',
      linkedin_url: 'https://linkedin.com/in/rohan-singh',
    },
    prospect_first_name: 'Rohan',
    research_text:
      'Acme is tightening counterfeit enforcement workflows and wants higher enforcement throughput without adding headcount.',
    offer_lock: 'Zeal 2.0',
    company_context: {
      company_name: 'Corsearch',
      company_url: 'https://corsearch.com',
      current_product: 'Zeal 2.0',
      cta_offer_lock: '',
      cta_type: 'event_invite',
      other_products: 'Trademark Watching\nDomain Monitoring',
      company_notes: 'Corsearch protects brands across 80+ marketplaces and 73 Fortune 100 companies.',
    },
    global_slider_state: {
      formality: 45,
      orientation: 65,
      length: 75,
      assertiveness: 60,
    },
  };
}

function makePresets() {
  return [
    { id: 'straight_shooter', name: 'Straight Shooter', frequency: 'Daily', sliders: {} },
    { id: 'headliner', name: 'Headliner', frequency: 'Daily', sliders: {} },
  ];
}

function waitTick() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

function makeBatchResponder(counter) {
  return async (payload) => {
    counter.count += 1;
    return {
      previews: payload.presets.map((preset) => ({
        preset_id: String(preset.preset_id),
        subject: `${preset.label} idea for ${payload.prospect.company}`,
        body: `Hi ${payload.prospect_first_name || 'there'},\n\nThis is a cached preview for ${preset.label}.\n\n${payload.cta_lock_text || 'Open to a 15-min call for a quick teardown + first-week sweep? Worth a look / Not a priority?'}`,
        vibeLabel: preset.label,
        vibeTags: ['Direct', 'Specific'],
        whyItWorks: ['Uses account context.', 'Keeps one offer lock.', 'Ends with one CTA.'],
      })),
      meta: { request_id: 'preview-test' },
    };
  };
}

test('opening preset modal twice does not re-fetch previews for unchanged context', async () => {
  const counter = { count: 0 };
  let context = makeContext();
  const library = new SDRPresetLibrary(null, {
    presets: makePresets(),
    autoRender: false,
    previewFetchDebounceMs: 0,
    getPreviewContext: () => context,
    generatePreviewBatch: makeBatchResponder(counter),
  });

  library.open();
  await waitTick();
  library.close();
  library.open();
  await waitTick();

  assert.equal(counter.count, 1);
});

test('switching presets does not re-fetch already cached previews for same context key', async () => {
  const counter = { count: 0 };
  const context = makeContext();
  const library = new SDRPresetLibrary(null, {
    presets: makePresets(),
    autoRender: false,
    previewFetchDebounceMs: 0,
    getPreviewContext: () => context,
    generatePreviewBatch: makeBatchResponder(counter),
  });

  library.open();
  await waitTick();
  assert.equal(counter.count, 1);

  library.setPreviewPreset('headliner');
  await waitTick();
  library.setPreviewPreset('straight_shooter');
  await waitTick();

  assert.equal(counter.count, 1);
});

test('changing preview inputs invalidates cache and triggers exactly one regeneration per new key', async () => {
  const counter = { count: 0 };
  let context = makeContext();
  const library = new SDRPresetLibrary(null, {
    presets: makePresets(),
    autoRender: false,
    previewFetchDebounceMs: 0,
    getPreviewContext: () => context,
    generatePreviewBatch: makeBatchResponder(counter),
  });

  library.open();
  await waitTick();
  assert.equal(counter.count, 1);

  context = { ...context, research_text: `${context.research_text} Added note from fresh deep research.` };
  library.refreshPreviews();
  await waitTick();
  assert.equal(counter.count, 2);

  library.refreshPreviews();
  await waitTick();
  assert.equal(counter.count, 2);
});
