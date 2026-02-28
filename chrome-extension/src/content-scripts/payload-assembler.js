export function build(extractedFields) {
  const accountId = extractAccountIdFromUrl() || extractRecordIdFromDom();

  const notesValue = extractedFields.notes?.value || '';
  const timelineValue = extractedFields.activityTimeline?.value || '';

  return {
    accountId,
    accountName: extractedFields.accountName?.value ?? null,
    industry: extractedFields.industry?.value ?? null,
    employeeCount: parseEmployeeCount(extractedFields.employeeCount?.value),
    openOpportunities: extractedFields.openOpportunities?.value ? [extractedFields.openOpportunities.value] : null,
    lastActivityDate: extractedFields.lastActivityDate?.value ?? null,
    notes: truncateNotes(notesValue),
    activityTimeline: timelineValue ? [`[Activity]: ${timelineValue}`] : [],
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

function extractRecordIdFromDom() {
  const el = document.querySelector('[data-record-id]');
  return el?.getAttribute('data-record-id') || null;
}

function parseEmployeeCount(value) {
  if (!value) return null;
  const num = parseInt(String(value).replace(/,/g, ''), 10);
  return Number.isNaN(num) ? null : num;
}

function buildConfidenceMap(extractedFields) {
  const map = {};
  for (const [field, data] of Object.entries(extractedFields)) {
    if (data?.confidence != null) map[field] = data.confidence;
  }
  return map;
}

function truncateNotes(text) {
  if (!text) return [];
  const limit = 5000;
  if (text.length <= limit) return [`[Notes field]: ${text}`];
  return [`[Notes field]: ${text.slice(0, limit)} [...truncated, ${text.length} chars total]`];
}
