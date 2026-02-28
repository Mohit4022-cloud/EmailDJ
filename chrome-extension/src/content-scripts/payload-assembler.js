/**
 * Payload Assembler — constructs the structured payload sent to Hub.
 *
 * IMPLEMENTATION INSTRUCTIONS:
 *
 * Exports: build(extractedFields) → PayloadObject
 *
 * PayloadObject schema:
 * {
 *   accountId: string,
 *   accountName: string,
 *   industry: string | null,
 *   employeeCount: number | null,
 *   openOpportunities: string[] | null,
 *   lastActivityDate: string | null,
 *   notes: string[],           // array of note strings with source labels
 *   activityTimeline: string[], // array of activity items
 *   extractionMetadata: {
 *     selectorConfidences: Record<string, number>,  // field → confidence score
 *     extractedAt: string,     // ISO timestamp
 *     salesforceUrl: string,   // current window.location.href
 *   }
 * }
 *
 * build(extractedFields):
 *   1. extractedFields is the output of queryWithFallback() calls for each field.
 *      Shape: { accountName: {value, confidence, selectorType}, industry: {...}, ... }
 *   2. Concatenate all Notes/Activity text into arrays:
 *      - Each notes item: "[Notes field]: {text}"
 *      - Each activity item: "[Activity {date}]: {text}"
 *   3. Build selectorConfidences map: { fieldName: confidence } for each extracted field.
 *   4. Estimate payload size. Target: ~2KB gzip.
 *      If notes text is very long (>5000 chars), truncate with a note:
 *      "[...truncated, {charCount} chars total]"
 *   5. IMPORTANT: Do NOT include any data that failed PII scrubbing.
 *      extractedFields should already be scrubbed before calling build().
 *   6. accountId: extract from current URL pattern /([a-zA-Z0-9]{15,18})/view
 *      or from the [data-record-id] attribute.
 *   7. Return the PayloadObject.
 */

/**
 * @param {Object} extractedFields - output of queryWithFallback() calls
 * @returns {Object} PayloadObject
 */
export function build(extractedFields) {
  // TODO: implement full payload assembly per instructions above
  const accountId = extractAccountIdFromUrl();

  return {
    accountId,
    accountName: extractedFields.accountName?.value ?? null,
    industry: extractedFields.industry?.value ?? null,
    employeeCount: parseEmployeeCount(extractedFields.employeeCount?.value),
    openOpportunities: null,  // TODO: extract from DOM
    lastActivityDate: extractedFields.lastActivityDate?.value ?? null,
    notes: extractedFields.notes?.value ? [`[Notes field]: ${extractedFields.notes.value}`] : [],
    activityTimeline: [],  // TODO: extract timeline items
    extractionMetadata: {
      selectorConfidences: buildConfidenceMap(extractedFields),
      extractedAt: new Date().toISOString(),
      salesforceUrl: window.location.href,
    },
  };
}

function extractAccountIdFromUrl() {
  const match = window.location.pathname.match(/\/([a-zA-Z0-9]{15,18})\/view/);
  return match ? match[1] : null;
}

function parseEmployeeCount(value) {
  if (!value) return null;
  const num = parseInt(value.replace(/,/g, ''), 10);
  return isNaN(num) ? null : num;
}

function buildConfidenceMap(extractedFields) {
  const map = {};
  for (const [field, data] of Object.entries(extractedFields)) {
    if (data?.confidence != null) map[field] = data.confidence;
  }
  return map;
}
