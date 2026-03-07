import test from 'node:test';
import assert from 'node:assert/strict';

import { debounce } from '../src/utils.js';

test('debounce keeps only last call in burst', async () => {
  const seen = [];
  const fn = debounce((value) => seen.push(value), 20);

  fn(1);
  fn(2);
  fn(3);

  await new Promise((resolve) => setTimeout(resolve, 40));
  assert.deepEqual(seen, [3]);
});
