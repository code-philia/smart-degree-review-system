const { getRuleDefinition } = require('../../rules/registry');

// This is deliberately an orchestration-only adapter. Existing detector
// implementations remain responsible for parsing PDFs and producing report
// runs; the runner only groups registry-backed rules by execution family.
async function runPaperLintRuleGroups({ pdfPath, selectedRuleIds, signal, runners, onGroupComplete }) {
  const groups = new Map();
  for (const ruleId of selectedRuleIds) {
    const family = getRuleDefinition(ruleId)?.family || 'legacy_bridge';
    if (!groups.has(family)) groups.set(family, []);
    groups.get(family).push(ruleId);
  }

  const tasks = [...groups].map(async ([family, ruleIds]) => {
    const runner = runners[family] || runners.legacy_bridge;
    if (typeof runner !== 'function') throw new Error(`未配置规则执行器：${family}`);
    const result = await runner(pdfPath, ruleIds, { signal });
    if (typeof onGroupComplete === 'function') await onGroupComplete({ family, ruleIds, result });
    return result;
  });
  return Promise.all(tasks);
}

module.exports = { runPaperLintRuleGroups };
