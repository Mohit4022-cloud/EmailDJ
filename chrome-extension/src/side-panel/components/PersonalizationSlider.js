/**
 * PersonalizationSlider — controls email generation style (0–10).
 *
 * IMPLEMENTATION INSTRUCTIONS:
 *
 * Exports: PersonalizationSlider (class)
 *
 * Constructor(container: HTMLElement, onChange: (value: number) => void):
 *   Renders the slider. Calls onChange when value changes.
 *
 * Slider design:
 *   - range input: min=0, max=10, step=1, default=5
 *   - Left label: "⚡ Efficiency" (slider=0)
 *     → short, direct email. 3 sentences max. Lead with business outcome. No fluff.
 *   - Right label: "🎯 Personalization" (slider=10)
 *     → deeply personalized. Reference specific details, news, personal pain points.
 *   - Center tooltip at current value showing description of what slider does.
 *
 * Slider value meanings (pass to Hub as slider_value param):
 *   0–2:  Efficiency tier (fastest generation, Tier 3 model eligible)
 *   3–7:  Balanced (Tier 2 model, mix of speed and personalization)
 *   8–10: High personalization (Tier 1/2 model, richer context used)
 *
 * getValue(): returns current integer value.
 * setValue(n): programmatically set the slider.
 *
 * UX note: SDRs should be trained that high personalization = slower generation
 * (2–5 seconds vs <2 seconds at low settings). Consider showing estimated
 * generation time next to slider: "~1s" at 0, "~3s" at 10.
 */

export class PersonalizationSlider {
  constructor(container, onChange) {
    this.container = container;
    this.onChange = onChange;
    this.value = 5;
    this.render();
  }

  render() {
    // TODO: implement DOM construction per instructions above
    this.container.innerHTML = `
      <div class="personalization-slider">
        <div class="slider-labels">
          <span class="label-left">⚡ Efficiency</span>
          <span class="label-right">🎯 Personalization</span>
        </div>
        <input type="range" id="persSlider" min="0" max="10" step="1" value="${this.value}"
               class="slider-input">
        <div class="slider-tooltip" id="sliderTooltip">Balanced</div>
      </div>
    `;

    const input = this.container.querySelector('#persSlider');
    input?.addEventListener('input', (e) => {
      this.value = parseInt(e.target.value, 10);
      this.updateTooltip();
      if (this.onChange) this.onChange(this.value);
    });
  }

  updateTooltip() {
    const tooltip = this.container.querySelector('#sliderTooltip');
    if (!tooltip) return;
    const descriptions = {
      0: 'Ultra-brief (~1s)',
      1: 'Very brief (~1s)',
      2: 'Brief (~1s)',
      3: 'Concise (~1.5s)',
      4: 'Concise (~1.5s)',
      5: 'Balanced (~2s)',
      6: 'Personalized (~2s)',
      7: 'Personalized (~2.5s)',
      8: 'High personalization (~3s)',
      9: 'Very personalized (~3s)',
      10: 'Maximum personalization (~4s)',
    };
    tooltip.textContent = descriptions[this.value] ?? 'Balanced';
  }

  getValue() {
    return this.value;
  }

  setValue(n) {
    this.value = Math.max(0, Math.min(10, n));
    const input = this.container.querySelector('#persSlider');
    if (input) input.value = String(this.value);
    this.updateTooltip();
  }
}
