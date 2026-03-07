import test from 'node:test';
import assert from 'node:assert/strict';

import { buildTraceMeta, buildValidationNotes, buildStageTimeline, classifyStudioStatus, humanizeStageName } from '../src/studioStatus.js';

test('classifyStudioStatus elevates failures and active generation states', () => {
  assert.deepEqual(classifyStudioStatus('Generating draft...', true), {
    title: 'Generating draft',
    tone: 'busy',
    detail: 'Generating draft...',
  });

  assert.deepEqual(classifyStudioStatus('Draft ready. Adjust sliders to remix.'), {
    title: 'Draft ready',
    tone: 'success',
    detail: 'Draft ready. Adjust sliders to remix.',
  });

  assert.deepEqual(classifyStudioStatus('Prospect name, title, and company are required.'), {
    title: 'Needs attention',
    tone: 'danger',
    detail: 'Prospect name, title, and company are required.',
  });
});

test('stage formatting maps stable pipeline stages to readable labels', () => {
  assert.equal(humanizeStageName('CONTEXT_SYNTHESIS'), 'Messaging Brief');
  assert.equal(humanizeStageName('EMAIL_REWRITE_SALVAGE'), 'Rewrite Salvage');
  assert.equal(humanizeStageName('custom_stage_name'), 'Custom Stage Name');
});

test('buildStageTimeline prefers final validation status when present', () => {
  const timeline = buildStageTimeline([
    {
      stage: 'EMAIL_QA',
      status: 'complete',
      elapsed_ms: 212,
      model: 'gpt-5-nano',
      raw_validation_status: 'passed',
      final_validation_status: 'passed_after_repair',
    },
  ]);

  assert.deepEqual(timeline, [
    {
      stage: 'EMAIL_QA',
      label: 'Deterministic QA',
      status: 'passed_after_repair',
      elapsedMs: 212,
      model: 'gpt-5-nano',
      rawValidationStatus: 'passed',
      finalValidationStatus: 'passed_after_repair',
    },
  ]);
});

test('buildValidationNotes surfaces validator drift and repair loop notes', () => {
  const notes = buildValidationNotes(
    [
      {
        stage: 'EMAIL_REWRITE',
        raw_validation_status: 'failed',
        final_validation_status: 'passed_after_repair',
      },
    ],
    {
      repaired: true,
      repair_attempt_count: 2,
      error: null,
    }
  );

  assert.deepEqual(notes, [
    {
      code: 'failed',
      message: 'Rewrite Pass: raw validation Failed',
    },
    {
      code: 'passed_after_repair',
      message: 'Rewrite Pass: final validation Passed After Repair',
    },
    {
      code: 'passed_after_repair',
      message: 'Deterministic repair loop ran 2 times.',
    },
  ]);
});

test('buildTraceMeta keeps the core done-payload identifiers', () => {
  assert.deepEqual(
    buildTraceMeta({
      trace_id: 'trace-123',
      prompt_template_hash: 'hash-456',
      prompt_template_version: 'v7',
      provider: 'openai',
      model: 'gpt-5-nano',
    }),
    [
      ['Trace ID', 'trace-123'],
      ['Prompt Hash', 'hash-456'],
      ['Prompt Version', 'v7'],
      ['Provider', 'openai'],
      ['Model', 'gpt-5-nano'],
    ]
  );
});
