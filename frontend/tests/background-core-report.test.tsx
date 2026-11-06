import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { LivePaperLintReport } from '../src/components/paperLint/LivePaperLintReport';
import { paperLintPresentation, numericExecutionWarnings } from '../src/components/paperLint/model';
import { buildExportReport } from '../src/utils/reportExport/model';
import { fixture } from './fixtures/reportExport';
import type { PaperLintRuleRun, PaperLintRule } from '../src/api/paperLint';
vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));
const coreId = 'required_section_completeness_check';
const keywordId = 'keyword_count_check';
const rules = [{ rule_id: coreId, title: '核心章节完整性' }, { rule_id: keywordId, title: '关键词数量' }] as PaperLintRule[];
const runs: PaperLintRuleRun[] = [
  { rule_id: coreId, rule_run_id: 'automatic-core', severity: 'warning', execution_status: 'completed', outcome: 'issues_found',
    params: { automatic_core_check: true }, findings: [{ rule_id: coreId, finding_id: 'missing-abstract', message: '缺少中文摘要' }] },
  { rule_id: keywordId, rule_run_id: 'keyword', severity: 'info', execution_status: 'unsupported', outcome: 'inconclusive',
    message: '未能检测：缺少中文摘要，无法检查关键词数量。', findings: [] },
];

it('exposes unselected automatic core findings in live filtering and exported scope without changing requested IDs', async () => {
  const selected = [keywordId];
  render(<LivePaperLintReport file={{ name: 'partial.pdf', url: '/partial.pdf' }} rules={rules} runs={runs} selectedRuleIds={selected} />);
  expect(screen.getByText('缺少中文摘要')).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const list = await screen.findByRole('listbox');
  expect(within(list).getByRole('option', { name: /^核心章节完整性/ })).toBeInTheDocument();
  const report = { ...fixture, selected_rule_ids: selected, result: { ...fixture.result, rule_runs: runs } };
  const exported = buildExportReport(report, rules, null);
  expect(exported.scope.find(x=>x.id===coreId)?.description).toContain('自动');
  expect(exported.findings.some(f=>f.message==='缺少中文摘要')).toBe(true);
  expect(report.selected_rule_ids).toEqual([keywordId]);
  expect(paperLintPresentation(paperLintPresentation(report.result))).toEqual(paperLintPresentation(report.result));
});

it('keeps a numeric check blocked by core structure visible in execution notices', () => {
  const numeric: PaperLintRuleRun = { ...runs[1], rule_id: 'abstract_numeric_consistency_check',
    params: { preconditions: [{ id: 'core_structure', passed: false, status: 'failed',
      reason: '未能检测：缺少中文摘要，无法可靠检查摘要数值声明与正文实验结果一致性。',
      suggestion: '请补齐或核对摘要和正文的核心章节后重新检测。' }] } };
  expect(numericExecutionWarnings(numeric)).toEqual([expect.objectContaining({
    ruleId: numeric.rule_id, reason: expect.stringContaining('缺少中文摘要'),
  })]);
});
