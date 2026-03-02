function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function toSliderNumber(value, fallback = 50) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return fallback;
  return clamp(Math.round(numeric), 0, 100);
}

function normalizeText(value) {
  return String(value || '').trim();
}

function normalizeLineBreaks(value) {
  return normalizeText(value).replace(/\r\n/g, '\n');
}

function compactWhitespace(value) {
  return normalizeText(value).replace(/\s+/g, ' ');
}

export function normalizeSliderState(raw = {}) {
  return {
    formality: toSliderNumber(raw.formality, 50),
    orientation: toSliderNumber(raw.orientation, 50),
    length: toSliderNumber(raw.length, 50),
    assertiveness: toSliderNumber(raw.assertiveness, 50),
  };
}

export function normalizePreviewContext(raw = {}) {
  const prospect = raw.prospect || {};
  const company = raw.company_context || {};

  return {
    prospect: {
      name: normalizeText(prospect.name),
      title: normalizeText(prospect.title),
      company: normalizeText(prospect.company),
      linkedin_url: normalizeText(prospect.linkedin_url),
    },
    research_text: normalizeLineBreaks(raw.research_text),
    company_context: {
      company_name: normalizeText(company.company_name),
      company_url: normalizeText(company.company_url),
      current_product: normalizeText(company.current_product),
      other_products: normalizeLineBreaks(company.other_products),
      company_notes: normalizeLineBreaks(company.company_notes),
    },
    global_slider_state: normalizeSliderState(raw.global_slider_state || {}),
  };
}

export function previewContextIdentity(context) {
  const normalized = normalizePreviewContext(context);
  return {
    prospectName: normalized.prospect.name,
    title: normalized.prospect.title,
    company: normalized.prospect.company,
    companyUrl: normalized.company_context.company_url,
    deepResearchPaste: normalized.research_text,
    companyNotes: normalized.company_context.company_notes,
    currentProductOrService: normalized.company_context.current_product,
    otherProductsServices: normalized.company_context.other_products,
    globalSliders: normalized.global_slider_state,
  };
}

export function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value ?? null);
}

export function hashString(input) {
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(16).padStart(8, '0');
}

export function buildPreviewContextHash(context) {
  return hashString(stableStringify(previewContextIdentity(context)));
}

export function buildPreviewCacheKey(contextHash, presetId) {
  return `${contextHash}:${presetId}`;
}

export function resolveEffectiveSliderState(globalSliderState, preset) {
  const base = normalizeSliderState(globalSliderState);
  const overrides = preset?.sliderOverrides || preset?.sliders || {};
  const next = { ...base };

  if (Object.prototype.hasOwnProperty.call(overrides, 'formal')) {
    next.formality = 100 - toSliderNumber(overrides.formal, 50);
  }
  if (Object.prototype.hasOwnProperty.call(overrides, 'outcome')) {
    next.orientation = toSliderNumber(overrides.outcome, 50);
  }
  if (Object.prototype.hasOwnProperty.call(overrides, 'long')) {
    next.length = toSliderNumber(overrides.long, 50);
  }
  if (Object.prototype.hasOwnProperty.call(overrides, 'diplomatic')) {
    next.assertiveness = toSliderNumber(overrides.diplomatic, 50);
  }
  return next;
}

export function sliderRowsFromState(sliderState) {
  const summary = normalizeSliderState(sliderState);
  return [
    {
      key: 'formality',
      label: 'Formal <-> Casual',
      left: 'Formal',
      right: 'Casual',
      leftValue: 100 - summary.formality,
      rightValue: summary.formality,
    },
    {
      key: 'orientation',
      label: 'Problem <-> Outcome',
      left: 'Problem',
      right: 'Outcome',
      leftValue: 100 - summary.orientation,
      rightValue: summary.orientation,
    },
    {
      key: 'length',
      label: 'Short <-> Long',
      left: 'Short',
      right: 'Long',
      leftValue: 100 - summary.length,
      rightValue: summary.length,
    },
    {
      key: 'assertiveness',
      label: 'Bold <-> Diplomatic',
      left: 'Bold',
      right: 'Diplomatic',
      leftValue: 100 - summary.assertiveness,
      rightValue: summary.assertiveness,
    },
  ];
}

export function buildWhyItWorksBullets(preset) {
  const fromPreset = Array.isArray(preset?.whyItWorksBullets)
    ? preset.whyItWorksBullets.map((item) => compactWhitespace(item)).filter(Boolean)
    : [];
  if (fromPreset.length > 0) return fromPreset.slice(0, 3);

  const text = compactWhitespace(preset?.whyItWorks);
  if (!text) return ['Grounded in current prospect context and clear business relevance.'];
  const sentences = text.split(/(?<=[.!?])\s+/).map((item) => item.trim()).filter(Boolean);
  if (sentences.length === 0) return [text];
  return sentences.slice(0, 3);
}

function toneTag(sliderState) {
  if (sliderState.formality >= 66) return 'Casual';
  if (sliderState.formality <= 34) return 'Formal';
  return 'Balanced Tone';
}

function framingTag(sliderState) {
  if (sliderState.orientation >= 66) return 'Outcome-Led';
  if (sliderState.orientation <= 34) return 'Problem-Led';
  return 'Balanced Framing';
}

function lengthTag(sliderState) {
  if (sliderState.length >= 66) return 'Long-Form';
  if (sliderState.length <= 34) return 'Short-Form';
  return 'Mid-Length';
}

function assertivenessTag(sliderState) {
  if (sliderState.assertiveness >= 66) return 'Diplomatic';
  if (sliderState.assertiveness <= 34) return 'Bold';
  return 'Measured';
}

export function buildVibeMetadata(preset, sliderState) {
  const label = compactWhitespace(preset?.vibeLabel || preset?.name || 'Preset');
  const candidateTags = Array.isArray(preset?.vibeTags)
    ? preset.vibeTags.map((tag) => compactWhitespace(tag)).filter(Boolean)
    : [];
  if (candidateTags.length >= 2) {
    return { label, tags: candidateTags.slice(0, 4) };
  }
  const tags = [toneTag(sliderState), framingTag(sliderState), lengthTag(sliderState), assertivenessTag(sliderState)];
  return { label, tags: tags.slice(0, 4) };
}

export function parseGeneratedDraft(rawDraft, fallbackCompany = '') {
  const normalized = normalizeLineBreaks(rawDraft);
  if (!normalized) {
    return {
      subject: `Quick idea for ${fallbackCompany || 'your team'}`,
      body: '',
    };
  }

  const lines = normalized.split('\n');
  const firstLineIndex = lines.findIndex((line) => normalizeText(line));
  if (firstLineIndex < 0) {
    return {
      subject: `Quick idea for ${fallbackCompany || 'your team'}`,
      body: '',
    };
  }

  const firstLine = lines[firstLineIndex].trim();
  const subjectMatch = firstLine.match(/^subject\s*:\s*(.+)$/i);
  if (subjectMatch) {
    const subject = subjectMatch[1].trim();
    const body = lines.slice(firstLineIndex + 1).join('\n').trim();
    return {
      subject: subject || `Quick idea for ${fallbackCompany || 'your team'}`,
      body,
    };
  }

  const likelySubject =
    firstLine.length <= 120 &&
    !/^hi[\s,]|^hello[\s,]|^dear[\s,]/i.test(firstLine) &&
    /[a-zA-Z]/.test(firstLine);
  if (likelySubject) {
    return {
      subject: firstLine,
      body: lines.slice(firstLineIndex + 1).join('\n').trim(),
    };
  }

  return {
    subject: `Quick idea for ${fallbackCompany || 'your team'}`,
    body: normalized,
  };
}

export function sanitizePlaceholderTokens(text, replacements = {}) {
  let sanitized = String(text || '');
  const map = {
    name: replacements.name || 'there',
    company: replacements.company || 'your company',
    title: replacements.title || 'your role',
    sender: replacements.sender || 'our team',
    mutual: replacements.mutual || 'a mutual contact',
  };

  const replacementsByPattern = [
    { pattern: /\[(name|first name|prospect name)\]/gi, value: map.name },
    { pattern: /\[(company|account|target company)\]/gi, value: map.company },
    { pattern: /\[(title|job title)\]/gi, value: map.title },
    { pattern: /\[(my name|sender name)\]/gi, value: map.sender },
    { pattern: /\[(mutual contact|referrer)\]/gi, value: map.mutual },
    { pattern: /\{\{\s*(name|first_name)\s*\}\}/gi, value: map.name },
    { pattern: /\{\{\s*(company|account_name)\s*\}\}/gi, value: map.company },
  ];

  for (const item of replacementsByPattern) {
    sanitized = sanitized.replace(item.pattern, item.value);
  }

  sanitized = sanitized.replace(/\[[^\]\n]{1,40}\]/g, '');
  sanitized = sanitized.replace(/[ \t]{2,}/g, ' ');
  sanitized = sanitized.replace(/\n{3,}/g, '\n\n');
  return sanitized.trim();
}

export function sanitizePreviewEmail(parts, context) {
  const normalized = normalizePreviewContext(context);
  const replacements = {
    name: normalized.prospect.name || 'there',
    company: normalized.prospect.company || 'your company',
    title: normalized.prospect.title || 'your role',
    sender: normalized.company_context.company_name || 'our team',
    mutual: 'a mutual contact',
  };

  const subject = sanitizePlaceholderTokens(parts?.subject, replacements);
  let body = sanitizePlaceholderTokens(parts?.body, replacements);
  if (!normalized.prospect.name) {
    body = body.replace(/^hi\s+[^,\n]+,/i, 'Hi there,');
    body = body.replace(/^hello\s+[^,\n]+,/i, 'Hello there,');
  }
  return {
    subject: subject || `Quick idea for ${normalized.prospect.company || 'your team'}`,
    body,
  };
}

