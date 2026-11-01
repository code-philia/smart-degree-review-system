const { StringDecoder } = require('string_decoder');

// JSONL progress shares stdout with the final engine result and initialization logs.
function createRuleProgressStream(ruleIds, onRuleComplete) {
  const decoder = new StringDecoder('utf8');
  const allowed = new Set(ruleIds);
  const seen = new Set();
  let pending = '';
  let writes = Promise.resolve();
  let failure;
  function line(value) {
    let event;
    try { event = JSON.parse(value); } catch { return; }
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

module.exports = { createRuleProgressStream };
