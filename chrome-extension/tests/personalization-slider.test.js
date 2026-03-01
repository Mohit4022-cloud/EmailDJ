import test from 'node:test';
import assert from 'node:assert/strict';

import { PersonalizationSlider } from '../src/side-panel/components/PersonalizationSlider.js';

class FakeInput {
  constructor() {
    this.value = '5';
    this.listeners = {};
  }

  addEventListener(type, cb) {
    this.listeners[type] = cb;
  }

  triggerInput(value) {
    this.value = String(value);
    const listener = this.listeners.input;
    if (listener) {
      listener({ target: { value: this.value } });
    }
  }
}

class FakeTextNode {
  constructor() {
    this.textContent = '';
  }
}

class FakeContainer {
  constructor() {
    this.nodes = new Map();
  }

  set innerHTML(_value) {
    this.nodes.set('#persSlider', new FakeInput());
    this.nodes.set('#sliderTooltip', new FakeTextNode());
  }

  querySelector(selector) {
    return this.nodes.get(selector) || null;
  }
}

test('slider emits onChange and updates tooltip text', () => {
  const container = new FakeContainer();
  const seen = [];
  const slider = new PersonalizationSlider(container, (value) => seen.push(value));

  const input = container.querySelector('#persSlider');
  const tooltip = container.querySelector('#sliderTooltip');

  input.triggerInput(9);
  assert.equal(slider.getValue(), 9);
  assert.equal(seen.at(-1), 9);
  assert.equal(tooltip.textContent, 'Very personalized (~3s)');

  slider.setValue(2);
  assert.equal(slider.getValue(), 2);
  assert.equal(input.value, '2');
  assert.equal(tooltip.textContent, 'Brief (~1s)');
  assert.equal(seen.at(-1), 2);
});
