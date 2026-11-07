import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const { coreStructureRun, mergeCoreRuns, attachCoreStructure, unavailableRuleRuns, CORE_RULE_ID } = require('../src/normative/paperStructureChecks');
const { toPaperLintResult } = require('../src/normative/localFiveRulePaperLintService');
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

it('counts explicitly selected core completeness findings as severe', () => {
  const result = toPaperLintResult({ rules: { '34': { status: 'completed', findings: [
    { message: '缺少中文摘要' },
  ] } } }, [CORE_RULE_ID]);
  expect(result.rule_runs[0].severity).toBe('error');
  expect(result.summary).toMatchObject({ error_finding_count: 1, warning_finding_count: 0 });
  expect(coreStructureRun(assessment(['结论'])).findings[0].severity).toBe('error');
});

it.each([
  ['sjtu_rule_18', '主体'], ['sjtu_rule_22', '参考文献'], ['sjtu_rule_24', '参考文献'],
  ['sjtu_rule_28', '目录'], ['sjtu_rule_31', '参考文献'], ['sjtu_rule_32', '参考文献'],
  ['sjtu_rule_33', '参考文献'], ['keyword_count_check', '摘要'],
  ['abstract_object_number_check', '英文摘要'], ['bilingual_abstract_consistency_check', '摘要'],
  ['bilingual_keywords_correspondence_check', '英文摘要'], ['abstract_numeric_consistency_check', '主体'],
  ['typo_detection_check', '主体'], ['chapter_new_page_check', '主体'],
])('does not add duplicate core alerts for the prerequisite of %s', (id, section) => {
  const admission = assessment([section]);
  const unavailable = unavailableRuleRuns(admission, [id]);
  const result = attachCoreStructure({ rule_runs: unavailable }, admission, [id]);
  expect(result.rule_runs.map(run=>run.rule_id)).toEqual([id]);
  expect(result.rule_runs[0]).toMatchObject({ execution_status: 'unsupported', outcome: 'inconclusive' });
  expect(result.rule_runs[0].message).toContain(section === '摘要' ? '中文摘要' : section);
  expect(coreStructureRun(admission, unavailable)).toBeNull();
});

it('keeps unrelated missing chapters severe while suppressing the explained chapter', () => {
  const admission = assessment(['摘要', '结论']);
  const unavailable = unavailableRuleRuns(admission, ['keyword_count_check']);
  const result = attachCoreStructure({ rule_runs: unavailable }, admission, ['keyword_count_check']);
  const core = result.rule_runs.find(run=>run.rule_id === CORE_RULE_ID);
  expect(core.findings.map(f=>f.message)).toEqual(['缺少结论：未在论文正文中识别到该章节。']);
  expect(result.summary).toMatchObject({ error_finding_count: 1, warning_finding_count: 0 });
});

it('keeps explicitly selected core alerts even when another rule explains the same prerequisite', () => {
  const admission = assessment(['摘要']);
  const unavailable = unavailableRuleRuns(admission, ['keyword_count_check']);
  const selected = toPaperLintResult({ rules: { '34': { status: 'completed', findings: [{ message: '缺少中文摘要' }] } } }, [CORE_RULE_ID]);
  const result = attachCoreStructure({ rule_runs: [...unavailable, ...selected.rule_runs] }, admission, ['keyword_count_check', CORE_RULE_ID]);
  expect(result.rule_runs.find(run=>run.rule_id===CORE_RULE_ID)).toMatchObject({ severity: 'error', outcome: 'issues_found' });
});

it('does not resurrect old automatic alerts when incrementally merging a prerequisite failure', () => {
  const admission = assessment(['摘要']);
  const old = { rule_runs: [coreStructureRun(admission)] };
  const unavailable = unavailableRuleRuns(admission, ['keyword_count_check']);
  const result = mergePaperLintResults(old, { rule_runs: unavailable }, ['keyword_count_check']);
  expect(result.rule_runs.map(run=>run.rule_id)).toEqual(['keyword_count_check']);
  expect(result.summary.finding_count).toBe(0);
});

it('deduplicates incomplete abstract prerequisites without hiding other defects', () => {
  const admission = assessment(['结论'], ['摘要']);
  const unavailable = unavailableRuleRuns(admission, ['keyword_count_check']);
  const result = attachCoreStructure({ rule_runs: unavailable }, admission, ['keyword_count_check']);
  expect(result.rule_runs[0].message).toContain('中文摘要不完整');
  expect(result.rule_runs.find(r=>r.rule_id===CORE_RULE_ID).findings).toHaveLength(1);
});
