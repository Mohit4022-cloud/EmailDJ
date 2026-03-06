import test from 'node:test';
import assert from 'node:assert/strict';

import { parseGeneratedDraft, sanitizePreviewEmail } from '../src/components/presetPreviewUtils.js';

function previewContext() {
  return {
    prospect: {
      name: 'Alex Doe',
      title: 'Head of RevOps',
      company: 'Acme',
    },
    company_context: {
      company_name: 'EmailDJ',
    },
  };
}

test('parseGeneratedDraft leaves subject empty when no valid draft text is present', () => {
  assert.deepEqual(parseGeneratedDraft('', 'Acme'), { subject: '', body: '' });
  assert.deepEqual(parseGeneratedDraft('Hi Alex,\n\nOpen to a quick chat?', 'Acme'), {
    subject: '',
    body: 'Hi Alex,\n\nOpen to a quick chat?',
  });
});

test('sanitizePreviewEmail does not synthesize a fallback subject', () => {
  const sanitized = sanitizePreviewEmail(
    {
      subject: '',
      body: 'Hi [Name],\n\nOpen to a quick chat to see if this is relevant?',
    },
    previewContext()
  );

  assert.equal(sanitized.subject, '');
  assert.match(sanitized.body, /^Hi Alex Doe,/);
});
