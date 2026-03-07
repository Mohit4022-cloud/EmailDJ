const STAGE_LABELS = {
  CONTEXT_SYNTHESIS: 'Messaging Brief',
  FIT_REASONING: 'Angle Fit',
  ANGLE_PICKER: 'Angle Selection',
  ONE_LINER_COMPRESSOR: 'Opener Compression',
  EMAIL_GENERATION: 'Draft Generation',
  EMAIL_QA: 'Deterministic QA',
  EMAIL_REWRITE: 'Rewrite Pass',
  EMAIL_REWRITE_SALVAGE: 'Rewrite Salvage',
};

function titleCase(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function humanizeStageName(stage) {
  const normalized = String(stage || '').trim().toUpperCase();
  if (!normalized) return 'Stage';
  return STAGE_LABELS[normalized] || titleCase(normalized);
}

export function classifyStudioStatus(text, pulse = false) {
  const detail = String(text || '').trim() || 'Ready. Fill inputs and click Generate.';
  const lower = detail.toLowerCase();

  if (
    /failed|error|required|session_not_found|timed out|integrity check/.test(lower) ||
    lower.startsWith('enter ') ||
    lower.startsWith('paste ')
  ) {
    return { title: 'Needs attention', tone: 'danger', detail };
  }
  if (/saved|copied/.test(lower)) {
    return { title: 'Draft captured', tone: 'success', detail };
  }
  if (/ready|complete|applied/.test(lower)) {
    return { title: 'Draft ready', tone: 'success', detail };
  }
  if (/remix/.test(lower)) {
    return { title: 'Remixing draft', tone: pulse ? 'busy' : 'neutral', detail };
  }
  if (/generat/.test(lower) || lower === 'working...') {
    return { title: 'Generating draft', tone: pulse ? 'busy' : 'neutral', detail };
  }
  if (/enrich|research|structuring/.test(lower)) {
    return { title: 'Refreshing context', tone: pulse ? 'busy' : 'neutral', detail };
  }
  if (pulse) {
    return { title: 'Working', tone: 'busy', detail };
  }
  return { title: 'Ready to steer', tone: 'neutral', detail };
}

export function buildStageTimeline(stageStats = [], liveStages = []) {
  const source = Array.isArray(stageStats) && stageStats.length ? stageStats : liveStages;
  return source.map((item) => {
    const stage = String(item?.stage || '').trim();
    const status = String(item?.final_validation_status || item?.status || 'pending').trim() || 'pending';
    const elapsedMs = Number(item?.elapsed_ms || 0);
    const model = String(item?.model || '').trim();
    const rawValidationStatus = String(item?.raw_validation_status || '').trim();
    const finalValidationStatus = String(item?.final_validation_status || '').trim();
    return {
      stage,
      label: humanizeStageName(stage),
      status,
      elapsedMs,
      model,
      rawValidationStatus,
      finalValidationStatus,
    };
  });
}

export function buildValidationNotes(stageStats = [], doneData = null) {
  const notes = [];
  for (const item of Array.isArray(stageStats) ? stageStats : []) {
    const stageLabel = humanizeStageName(item?.stage);
    const rawStatus = String(item?.raw_validation_status || '').trim();
    const finalStatus = String(item?.final_validation_status || '').trim();
    const error = String(item?.error || item?.first_error || '').trim();
    if (rawStatus && !['pending', 'passed'].includes(rawStatus)) {
      notes.push({ code: rawStatus, message: `${stageLabel}: raw validation ${titleCase(rawStatus)}` });
    }
    if (finalStatus && !['pending', 'passed'].includes(finalStatus)) {
      notes.push({ code: finalStatus, message: `${stageLabel}: final validation ${titleCase(finalStatus)}` });
    }
    if (error) {
      notes.push({ code: error, message: `${stageLabel}: ${titleCase(error)}` });
    }
  }

  if (doneData?.repaired) {
    const count = Number(doneData?.repair_attempt_count || 1);
    notes.push({
      code: 'passed_after_repair',
      message: `Deterministic repair loop ran ${count} time${count === 1 ? '' : 's'}.`,
    });
  }

  if (doneData?.error?.message) {
    notes.push({
      code: String(doneData.error.code || 'error'),
      message: String(doneData.error.message),
    });
  }

  const seen = new Set();
  return notes.filter((item) => {
    const key = `${item.code}:${item.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function buildTraceMeta(doneData = null) {
  if (!doneData || typeof doneData !== 'object') return [];
  const items = [
    ['Trace ID', String(doneData.trace_id || '').trim()],
    ['Prompt Hash', String(doneData.prompt_template_hash || '').trim()],
    ['Prompt Version', String(doneData.prompt_template_version || '').trim()],
    ['Provider', String(doneData.provider || '').trim()],
    ['Model', String(doneData.model || '').trim()],
  ];
  return items.filter(([, value]) => value);
}
