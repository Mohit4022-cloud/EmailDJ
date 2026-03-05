import test from 'node:test';
import assert from 'node:assert/strict';

import { applyStreamEvent, createStreamState } from '../src/streamContract.js';

test('discard stale generation tokens and always apply done.final.body', () => {
  const state = createStreamState();
  const accepted = [];

  const events = [
    { event: 'start', data: { generation_id: 'gen-a', draft_id: 1 } },
    { event: 'token', data: { generation_id: 'gen-a', draft_id: 1, token: 'old ' } },
    // Mid-stream preset switch to new generation.
    { event: 'start', data: { generation_id: 'gen-b', draft_id: 2 } },
    { event: 'token', data: { generation_id: 'gen-a', draft_id: 1, token: 'stale ' } },
    { event: 'token', data: { generation_id: 'gen-b', draft_id: 2, token: 'new ' } },
    // Reconnect on same generation should continue, not reset.
    { event: 'start', data: { generation_id: 'gen-b', draft_id: 2 } },
    { event: 'token', data: { generation_id: 'gen-b', draft_id: 2, token: 'draft ' } },
    // Stale done must be ignored.
    { event: 'done', data: { generation_id: 'gen-a', draft_id: 1, final: { body: 'OLD BODY' } } },
    { event: 'done', data: { generation_id: 'gen-b', draft_id: 2, final: { body: 'FINAL BODY' } } },
  ];

  let finalBody = '';
  for (const msg of events) {
    const outcome = applyStreamEvent(state, msg);
    if (outcome.reset) accepted.length = 0;
    if (outcome.appendToken) accepted.push(outcome.appendToken);
    if (outcome.done && typeof outcome.finalBody === 'string') {
      finalBody = outcome.finalBody;
    }
  }

  assert.equal(state.activeGenerationId, 'gen-b');
  assert.equal(state.activeDraftId, 2);
  assert.equal(accepted.join(''), 'new draft ');
  assert.equal(state.streamBuffer, 'new draft ');
  assert.equal(finalBody, 'FINAL BODY');
});

test('done variants payload uses first successful variant as final content', () => {
  const state = createStreamState();
  const outcome = applyStreamEvent(state, {
    event: 'done',
    data: {
      generation_id: 'gen-v',
      draft_id: 4,
      ok: true,
      variants: [
        { preset_id: 'direct', error: { code: 'VALIDATION_FAILED', message: 'failed' } },
        { preset_id: 'challenger', subject: 'Variant subject', body: 'Variant body' },
      ],
    },
  });

  assert.equal(outcome.accepted, true);
  assert.equal(outcome.done, true);
  assert.equal(outcome.finalSubject, 'Variant subject');
  assert.equal(outcome.finalBody, 'Variant body');
});
