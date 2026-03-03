export function createStreamState() {
  return {
    activeGenerationId: null,
    activeDraftId: null,
    streamBuffer: '',
    tokenCount: 0,
    expectedChunkIndex: 0,
    chunkSequenceMismatch: false,
    doneData: null,
    streamError: '',
  };
}

function _eventGenerationId(msg) {
  const id = msg?.data?.generation_id;
  return typeof id === 'string' && id.trim() ? id.trim() : null;
}

function _eventDraftId(msg) {
  const id = msg?.data?.draft_id;
  return typeof id === 'number' ? id : null;
}

function _isStaleGeneration(state, msg) {
  const eventGenerationId = _eventGenerationId(msg);
  if (!eventGenerationId || !state.activeGenerationId) return false;
  return eventGenerationId !== state.activeGenerationId;
}

export function applyStreamEvent(state, msg) {
  if (!msg || typeof msg !== 'object') return { accepted: false };

  if (msg.event === 'start') {
    const generationId = _eventGenerationId(msg);
    const draftId = _eventDraftId(msg);
    let reset = false;
    if (generationId && state.activeGenerationId && generationId !== state.activeGenerationId) {
      // Mid-stream preset switch: reset stream assembly on the new generation.
      state.streamBuffer = '';
      state.tokenCount = 0;
      state.expectedChunkIndex = 0;
      state.chunkSequenceMismatch = false;
      state.doneData = null;
      reset = true;
    }
    if (generationId) state.activeGenerationId = generationId;
    if (draftId !== null) state.activeDraftId = draftId;
    return { accepted: true, event: 'start', reset };
  }

  if (msg.event === 'token') {
    if (_isStaleGeneration(state, msg)) {
      return { accepted: false, stale: true };
    }
    const generationId = _eventGenerationId(msg);
    if (!state.activeGenerationId && generationId) {
      state.activeGenerationId = generationId;
    }
    const draftId = _eventDraftId(msg);
    if (draftId !== null && state.activeDraftId === null) {
      state.activeDraftId = draftId;
    }

    const chunkIndex = msg.data?.chunk_index;
    if (typeof chunkIndex === 'number') {
      if (chunkIndex !== state.expectedChunkIndex) state.chunkSequenceMismatch = true;
      state.expectedChunkIndex = chunkIndex + 1;
    }

    const token = msg.data?.token || '';
    if (!token) return { accepted: false };
    state.tokenCount += 1;
    state.streamBuffer += token;
    return { accepted: true, appendToken: token };
  }

  if (msg.event === 'done') {
    if (_isStaleGeneration(state, msg)) {
      return { accepted: false, stale: true };
    }
    const generationId = _eventGenerationId(msg);
    if (!state.activeGenerationId && generationId) {
      state.activeGenerationId = generationId;
    }
    const draftId = _eventDraftId(msg);
    if (draftId !== null && state.activeDraftId === null) {
      state.activeDraftId = draftId;
    }
    state.doneData = msg.data || null;
    const finalBody = typeof msg?.data?.final?.body === 'string' ? msg.data.final.body : null;
    return { accepted: true, done: true, finalBody, doneData: state.doneData };
  }

  if (msg.event === 'error') {
    state.streamError = String(msg.data?.error || 'Draft generation failed during stream.');
    return { accepted: true, error: state.streamError };
  }

  return { accepted: false };
}
