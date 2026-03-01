import test from 'node:test';
import assert from 'node:assert/strict';

import { scrub } from '../src/content-scripts/pii-prefilter.js';

test('scrub redacts supported PII patterns and preserves non-PII', () => {
  const input = 'Contact jane@example.com or 303-555-1212. SSN 111-22-3333. Card 4242 4242 4242 4242. Keep Acme launch plan.';
  const { redacted, tokenMap } = scrub(input);

  assert.equal(Object.keys(tokenMap).length, 4);
  assert.ok(redacted.includes('[EMAIL_1]'));
  assert.ok(redacted.includes('[PHONE_1]'));
  assert.ok(redacted.includes('[SSN_1]'));
  assert.ok(redacted.includes('[CREDIT_1]'));
  assert.ok(redacted.includes('Acme launch plan'));
  assert.equal(tokenMap['[EMAIL_1]'], 'jane@example.com');
  assert.equal(tokenMap['[PHONE_1]'], '303-555-1212');
  assert.equal(tokenMap['[SSN_1]'], '111-22-3333');
  assert.equal(tokenMap['[CREDIT_1]'], '4242 4242 4242 4242');
});

test('scrub handles non-string inputs deterministically', () => {
  const { redacted, tokenMap } = scrub(null);
  assert.equal(redacted, '');
  assert.deepEqual(tokenMap, {});
});
