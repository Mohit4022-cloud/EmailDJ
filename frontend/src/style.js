function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function sliderToAxis(value) {
  const v = clamp(Number(value), 0, 100);
  return Number(((v - 50) / 50).toFixed(2));
}

export function styleToPayload(sliderState) {
  return {
    formality: sliderToAxis(sliderState.formality),
    orientation: sliderToAxis(sliderState.orientation),
    length: sliderToAxis(sliderState.length),
    assertiveness: sliderToAxis(sliderState.assertiveness),
  };
}

export function styleKey(style) {
  return `f:${style.formality}|o:${style.orientation}|l:${style.length}|a:${style.assertiveness}`;
}
