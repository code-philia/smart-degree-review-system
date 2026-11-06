import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const { coreStructureRun, mergeCoreRuns, unavailableRuleRuns, CORE_RULE_ID } = require('../src/normative/paperStructureChecks');
const { mergePaperLintResults } = require('../src/normative/reviewPilotPaperLintService');
const required = ['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'];
function assessment(missing = [], incomplete = [], profile = 'chinese-thesis') {
  return { status: 'accepted', stage: missing.length || incomplete.length ? 'partial' : 'complete',
    structure: { profile, required_sections: profile === 'chinese-thesis' ? required : required.filter(x => x !== '英文摘要'),
      missing_sections: missing, incomplete_sections: incomplete,
      observed_sections: Object.fromEntries(required.map(name => [name, !missing.includes(name)])),
      abstract_sections: Object.fromEntries(['摘要','英文摘要'].filter(x=>!missing.includes(x)).map(name=>[name,
        { status: incomplete.includes(name) ? 'incomplete' : 'complete', has_keywords: !incomplete.includes(name), issues: ['未识别到本摘要的非空关键词收尾'] }])) } };
}

it('reports unselected Chinese/English core defects without adding optional cover requirements', () => {
  const run = coreStructureRun(assessment(['摘要'], ['英文摘要']));
  expect(run.rule_id).toBe(CORE_RULE_ID);
  expect(run.params.automatic_core_check).toBe(true);
  expect(run.findings.map(f=>f.message)).toEqual([
    '缺少中文摘要：未在论文正文中识别到该章节。',
    '英文摘要（Abstract）不完整：未识别到本摘要的非空关键词收尾。',
  ]);
  expect(JSON.stringify(run)).not.toMatch(/声明|授权|封面|题名页/);
  expect(coreStructureRun(assessment())).toBeNull();
});

it('merges selected and background core findings once, retaining optional normative findings', () => {
  const automatic = coreStructureRun(assessment(['摘要']));
  const selected = { ...automatic, params: null, findings: [
    { ...automatic.findings[0], finding_id: 'selected-native', location: { type: 'pdf_page', page_number: 2 } },
    { finding_id: 'declaration', rule_id: CORE_RULE_ID, message: '缺少原创性声明' },
  ] };
  const run = mergeCoreRuns(selected, automatic);
  expect(run.findings).toHaveLength(2);
  expect(run.findings[0].location.page_number).toBe(2);
  expect(mergeCoreRuns(run, automatic).findings).toEqual(run.findings);
});

it('keeps background core findings through incremental result merging without selecting the rule', () => {
  const core = coreStructureRun(assessment(['摘要']));
  const old = { type: 'paper_lint', rule_runs: [core] };
  const fresh = { rule_runs: [{ rule_id: 'keyword_count_check', execution_status: 'unsupported', outcome: 'inconclusive', findings: [] }] };
  const result = mergePaperLintResults(old, fresh, ['keyword_count_check']);
  expect(result.rule_runs.map(r=>r.rule_id)).toEqual(['keyword_count_check', CORE_RULE_ID]);
  expect(result.summary.finding_count).toBe(1);
});

it('marks only checks lacking their required evidence as unavailable', () => {
  const ids = ['keyword_count_check','sjtu_rule_31','sjtu_rule_32','sjtu_rule_18','chinese_english_symbol_mix_check'];
  const runs = unavailableRuleRuns(assessment(['摘要','关键词']), ids);
  expect(runs.map(r=>r.rule_id)).toEqual(['keyword_count_check']);
  expect(runs[0]).toMatchObject({ execution_status: 'unsupported', outcome: 'inconclusive', findings: [] });
  expect(runs[0].message).toContain('中文摘要');
  expect(unavailableRuleRuns(assessment(['英文摘要']), ids)).toEqual([]);
  expect(unavailableRuleRuns(assessment([], ['摘要']), ids)[0].message).toContain('关键词');
});

it('does not prescribe a Chinese abstract to an English thesis', () => {
  const valid = assessment([], [], 'english-thesis');
  expect(unavailableRuleRuns(valid, ['keyword_count_check'])).toEqual([]);
  expect(coreStructureRun(assessment(['摘要'], [], 'english-thesis')).findings[0].message).toContain('英文摘要（Abstract）');
});

it('provides a structured prerequisite for numeric execution-warning adapters', () => {
  const [run] = unavailableRuleRuns(assessment(['摘要']), ['abstract_numeric_consistency_check']);
  expect(run.params.preconditions).toEqual([expect.objectContaining({ id: 'core_structure', passed: false,
    status: 'failed', reason: run.message })]);
});
