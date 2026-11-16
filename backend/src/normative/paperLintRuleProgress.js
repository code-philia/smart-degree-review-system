const { StringDecoder } = require('string_decoder');

// JSONL progress shares stdout with the final engine result and initialization logs.
function createRuleProgressStream(ruleIds, onRuleComplete, { taskId, onWorkProgress } = {}) {
  const decoder = new StringDecoder('utf8');
  const allowed = new Set(ruleIds);
  const seen = new Set();
  let pending = '';
  let writes = Promise.resolve();
  let failure;
  const completedChunks = new Set();
  let totalChunks;
  function line(value) {
    let event;
    try { event = JSON.parse(value); } catch { return; }
    if (event?.type === 'paper_lint_chunk_complete') {
      if (!onWorkProgress || !taskId || event.task_id !== taskId
        || event.rule_id !== 'typo_detection_check' || !allowed.has(event.rule_id)
        || event.execution_status !== 'completed'
        || !Number.isSafeInteger(event.total_chunks) || event.total_chunks < 1 || event.total_chunks > 1000000
        || totalChunks !== undefined && totalChunks !== event.total_chunks
        || !Number.isSafeInteger(event.chunk_index) || event.chunk_index < 0 || event.chunk_index >= event.total_chunks
        || completedChunks.has(event.chunk_index)
        || event.completed_chunks !== completedChunks.size + 1) return;
      totalChunks = event.total_chunks;
      completedChunks.add(event.chunk_index);
      onWorkProgress(event);
      return;
    }
    const run = event?.rule_run;
    if (event?.type !== 'paper_lint_rule_complete' || !allowed.has(run?.rule_id)
      || seen.has(run.rule_id) || !Array.isArray(run.findings)
      || !['completed', 'unsupported', 'error'].includes(run.execution_status)) return;
    seen.add(run.rule_id);
    writes = writes.then(() => { if (!failure) return onRuleComplete(run); })
      .catch(error => { failure ||= error; });
  }
  return {
    write(chunk) {
      pending += decoder.write(chunk);
      const lines = pending.split('\n');
      pending = lines.pop();
      for (const value of lines) line(value);
    },
    async finish() {
      pending += decoder.end();
      if (pending.trim()) line(pending);
      pending = '';
      await writes;
      if (failure) throw failure;
    },
  };
}

// Progress may renew idle time only inside an independently fixed absolute cap.
// Callers supply this callback solely for validated private operator work.
function createRunTimeout({ timeoutMs, maximumMs = timeoutMs, signal, onTimeout }) {
  let idleTimer;
  let absoluteTimer;
  let closed = false;
  function clear() {
    closed = true;
    clearTimeout(idleTimer);
    clearTimeout(absoluteTimer);
    signal?.removeEventListener('abort', clear);
  }
  function expire() {
    if (closed) return;
    clear();
    onTimeout();
  }
  function progress() {
    if (closed || signal?.aborted) return;
    clearTimeout(idleTimer);
    idleTimer = setTimeout(expire, timeoutMs);
  }
  absoluteTimer = setTimeout(expire, maximumMs);
  signal?.addEventListener('abort', clear, { once: true });
  if (signal?.aborted) clear(); else progress();
  return { progress, clear };
}

module.exports = { createRuleProgressStream, createRunTimeout };
