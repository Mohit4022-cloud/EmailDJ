const SLIDERS = [
  {
    key: 'formality',
    title: 'Formal to Casual',
    left: 'Formal',
    right: 'Casual',
    copy: 'Adjust the voice while preserving the same core message and factual anchors.',
  },
  {
    key: 'orientation',
    title: 'Problem-Led to Outcome-Led',
    left: 'Problem',
    right: 'Outcome',
    copy: 'Tune how the draft frames urgency without changing the underlying narrative.',
  },
  {
    key: 'length',
    title: 'Short ↔ Long',
    left: 'Short',
    right: 'Long',
    copy: 'Expand or compress the same brief rather than re-materializing a new storyline.',
  },
  {
    key: 'assertiveness',
    title: 'Bold ↔ Diplomatic',
    left: 'Bold',
    right: 'Diplomatic',
    copy: 'Change the pressure and posture while keeping the same CTA and proof logic.',
  },
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export class SliderBoard {
  constructor(container, onChange) {
    this.container = container;
    this.onChange = onChange;
    this.sliderRefs = new Map();
    this.values = {
      formality: 50,
      orientation: 50,
      length: 50,
      assertiveness: 50,
    };
    this.render();
  }

  render() {
    this.container.innerHTML = `
      <section class="steering-panel">
        <div class="steering-head">
          <div>
            <p class="eyebrow">Message Steering</p>
            <h3>Shape the expression, not the brief</h3>
          </div>
          <p class="meta-copy">Presets and sliders preserve the same narrative, proof, and CTA.</p>
        </div>
        <div class="steering-grid">
          ${SLIDERS.map((slider) => `
            <article class="slider-card" data-slider-card="${slider.key}">
              <div class="slider-card-head">
                <div>
                  <p class="slider-kicker">${slider.title}</p>
                  <h4 class="slider-lean" data-slider-lean="${slider.key}"></h4>
                </div>
                <div class="slider-value" data-slider-value="${slider.key}">${this.values[slider.key]}%</div>
              </div>
              <p class="slider-copy">${slider.copy}</p>
              <div class="slider-meter">
                <div class="slider-meter-fill" data-slider-fill="${slider.key}"></div>
              </div>
              <div class="slider-labels"><span>${slider.left}</span><span>${slider.right}</span></div>
              <input data-slider="${slider.key}" type="range" min="0" max="100" step="1" value="${this.values[slider.key]}"/>
            </article>
          `).join('')}
        </div>
      </section>
    `;

    this.sliderRefs.clear();
    for (const slider of SLIDERS) {
      this.sliderRefs.set(slider.key, {
        input: this.container.querySelector(`input[data-slider="${slider.key}"]`),
        fill: this.container.querySelector(`[data-slider-fill="${slider.key}"]`),
        lean: this.container.querySelector(`[data-slider-lean="${slider.key}"]`),
        value: this.container.querySelector(`[data-slider-value="${slider.key}"]`),
      });
      this.syncSlider(slider.key);
    }

    this.container.querySelectorAll('input[data-slider]').forEach((el) => {
      el.addEventListener('input', (event) => {
        const key = event.target.dataset.slider;
        this.values[key] = Number(event.target.value);
        this.syncSlider(key);
        if (this.onChange) this.onChange(this.getValues());
      });
    });
  }

  describeSlider(slider, value) {
    if (value <= 34) return `Leaning ${slider.left.toLowerCase()}`;
    if (value >= 66) return `Leaning ${slider.right.toLowerCase()}`;
    return 'Balanced mix';
  }

  syncSlider(key) {
    const slider = SLIDERS.find((item) => item.key === key);
    const refs = this.sliderRefs.get(key);
    if (!slider || !refs) return;
    const value = clamp(this.values[key], 0, 100);
    if (refs.fill) refs.fill.style.width = `${value}%`;
    if (refs.value) refs.value.textContent = `${value}%`;
    if (refs.lean) refs.lean.textContent = this.describeSlider(slider, value);
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
      this.syncSlider(key);
    }

    if (emit && this.onChange) this.onChange(this.getValues());
  }
}
