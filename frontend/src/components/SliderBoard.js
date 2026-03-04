const SLIDERS = [
  {
    key: 'formality',
    title: 'Formal ↔ Casual',
    left: 'Formal',
    right: 'Casual',
  },
  {
    key: 'orientation',
    title: 'Problem-Led ↔ Outcome-Led',
    left: 'Problem',
    right: 'Outcome',
  },
  {
    key: 'length',
    title: 'Short ↔ Long',
    left: 'Short',
    right: 'Long',
  },
  {
    key: 'assertiveness',
    title: 'Bold ↔ Diplomatic',
    left: 'Bold',
    right: 'Diplomatic',
  },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export class SliderBoard {
  constructor(container, onChange) {
    this.container = container;
    this.onChange = onChange;
    this.values = {
      formality: 50,
      orientation: 50,
      length: 50,
      assertiveness: 50,
    };
    this.render();
  }

  render() {
    this.container.innerHTML = `<div class="slider-grid">${SLIDERS.map((s) => `
      <div class="slider">
        <div class="title">${s.title}</div>
        <div class="labels"><span>${s.left}</span><span>${s.right}</span></div>
        <input data-slider="${s.key}" type="range" min="0" max="100" step="1" value="${this.values[s.key]}"/>
      </div>
    `).join('')}</div>`;

    this.container.querySelectorAll('input[data-slider]').forEach((el) => {
      el.addEventListener('input', (event) => {
        const key = event.target.dataset.slider;
        this.values[key] = Number(event.target.value);
        if (this.onChange) this.onChange(this.getValues());
      });
    });
  }

  getValues() {
    return { ...this.values };
  }

  setValues(nextValues, options = {}) {
    const emit = Boolean(options.emit);
    if (!nextValues || typeof nextValues !== 'object') return;

    for (const slider of SLIDERS) {
      const key = slider.key;
      if (typeof nextValues[key] !== 'number' || Number.isNaN(nextValues[key])) continue;
      this.values[key] = clamp(Math.round(nextValues[key]), 0, 100);
      const input = this.container.querySelector(`input[data-slider="${key}"]`);
      if (input) input.value = String(this.values[key]);
    }

    if (emit && this.onChange) this.onChange(this.getValues());
  }
}
