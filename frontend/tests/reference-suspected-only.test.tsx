import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings, paperLintPresentation } from '../src/components/paperLint/model';
import { LivePaperLintReport } from '../src/components/paperLint/LivePaperLintReport';
import { buildExportReport, reportText } from '../src/utils/reportExport/model';
import { fixture } from './fixtures/reportExport';

vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));

const id = 'sjtu_rule_32';
const rules = [{ rule_id: id, title: '引用的外部文献不存在' }] as PaperLintRule[];
const base: PaperLintRuleRun = { rule_id: id, rule_run_id: 'refs', severity: 'warning', execution_status: 'completed', outcome: 'inconclusive',
  message: '已核验存在 109/161 条参考文献。52 条待核查。参考文献列表提取不完整。',
  params: { reference_verification: { total: 161, verified: 109, unresolved: 52 } }, findings: [] };
const callbacks = { onFindingClick: vi.fn(), onAnchorClick: vi.fn(), activeFindingKey: null, activeAnchorId: null };

it('shows historical unresolved references as Info and keeps export and API summary counts aligned', () => {
  const run = { ...base, compiler_diagnostics: [1, 2].map(n => ({ node_id: `ref-${n}`, check_id: 'existence',
    status: 'UNKNOWN' as const, reasons: ['reference_not_matched'], evidence: [],
    location: { type: 'pdf_page' as const, page_number: 20 + n } })) };
  const result = { ...fixture.result, rule_runs: [run] };
  const view = paperLintPresentation(result);
  expect(view.summary).toMatchObject({ info_finding_count: 2, warning_finding_count: 0 });
  expect(view.rule_runs[0].outcome).toBe('inconclusive');
  expect(view.rule_runs[0].publication_status).toBe('NO_ALERT');
  expect(paperLintPresentation(view)).toEqual(view);
  const findings = flattenPaperLintFindings(result);
  render(<FindingsPane {...callbacks} rules={rules} selectedRuleIds={[id]} ruleRuns={[view.rule_runs[0]]} findings={findings} />);
  fireEvent.click(screen.getByRole('button', { name: '提示 2', exact: true }));
  expect(screen.getAllByText('引用核验证据不足，请人工核查。')).toHaveLength(2);
  expect(screen.getByRole('button', { name: '警告 0', exact: true })).toBeInTheDocument();
  expect(buildExportReport({ ...fixture, result }, rules, null).summary.info_finding_count).toBe(2);
});

it.each([false, true])('shows a green zero for completed insufficient evidence in saved/live reports (live=%s)', async running => {
  render(<FindingsPane {...callbacks} running={running} rules={rules} selectedRuleIds={[id]} ruleRuns={[base]} findings={[]} />);
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const row = within(await screen.findByRole('listbox')).getByRole('option', { name: '引用的外部文献不存在，问题总数 0 处' });
  expect(row).toHaveTextContent('0');
  row.focus(); fireEvent.keyDown(row, { key: 'Enter' });
  expect(screen.getByText('未发现疑似不存在的引用')).toBeInTheDocument();
  expect(screen.getByTestId('rule-empty-icon')).toHaveClass('text-success-600');
  expect(screen.queryByText(/52 条待核查|提取不完整|暂无法判定/)).not.toBeInTheDocument();
});

it('does not turn legacy search-miss prompts into visible findings', () => {
  const run = { ...base, findings: [{ finding_id: 'old-miss', rule_id: id, check_id: 'work_existence', prompt_only: true,
    message: '未在 SerpAPI 中查到该参考文献，请人工复核。' }] };
  expect(flattenPaperLintFindings({ rule_runs: [run] })).toEqual([]);
});

it.each([false, true])('lists supported suspicions individually under Info with their source and PDF location (live=%s)', async running => {
  const run = { ...base, outcome: 'issues_found' as const, findings: [1, 2].map(n => ({ finding_id: `suspect-${n}`, rule_id: id,
    message: `可核查的明确疑点 ${n}`, evidence: [{ id: `source-${n}`, kind: 'source_span', quote: `[${n}] 完整参考文献 ${n}` }],
    location: { type: 'pdf_page' as const, page_number: 20 + n }, suggestion: '请人工复核该条引用。' })) };
  const findings = flattenPaperLintFindings({ rule_runs: [run] });
  expect(findings.every(item => item.ruleRun.severity === 'info')).toBe(true);
  render(<FindingsPane {...callbacks} running={running} rules={rules} selectedRuleIds={[id]} ruleRuns={[run]} findings={findings} />);
  expect(screen.getByRole('button', { name: '警告 0', exact: true })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '提示 2', exact: true }));
  for (const n of [1, 2]) {
    expect(screen.getByText(`可核查的明确疑点 ${n}`)).toBeInTheDocument();
    expect(screen.getByText(`[${n}] 完整参考文献 ${n}`)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: `跳到 PDF 第 ${20 + n} 页` })).toBeInTheDocument();
  }
  expect(screen.queryByText(/52 条待核查/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '跳到 PDF 第 21 页' }));
  expect(callbacks.onFindingClick).toHaveBeenCalledWith('suspect-1');
});

it('keeps an actual reference detector execution error visible', () => {
  render(<FindingsPane {...callbacks} rules={rules} selectedRuleIds={[id]} ruleRuns={[{ ...base, execution_status: 'error' }]} findings={[]} />);
  expect(screen.getByRole('combobox')).toHaveTextContent('检测失败');
});

it('does not contradict a completed green-zero rule with an undecided live-report banner', () => {
  render(<LivePaperLintReport file={{ name: 'paper.pdf', url: '/paper.pdf' }} rules={rules} runs={[base]} selectedRuleIds={[id]} />);
  expect(screen.queryByText(/暂无法判定|52 条待核查/)).not.toBeInTheDocument();
});

it.each([false, true])('keeps historical export totals and conclusions consistent with visible reference findings (supported=%s)', supported => {
  const run = { ...base, findings: [{ finding_id: 'old-ref', rule_id: id, prompt_only: !supported,
    message: supported ? '有充分证据的引用疑点' : '未在 SerpAPI 中查到' }] };
  const report = { ...fixture, result: { ...fixture.result, rule_runs: [run], summary: { ...fixture.result.summary,
    finding_count: 1, warning_finding_count: 1, error_finding_count: 0, info_finding_count: 0 } } };
  const original = JSON.stringify(report);
  const model = buildExportReport(report, rules, null);
  expect(model.summary).toMatchObject({ finding_count: supported ? 1 : 0, warning_finding_count: 0, info_finding_count: supported ? 1 : 0 });
  expect(model.rules[0].finding_count).toBe(supported ? 1 : 0);
  if (!supported) expect(reportText(model)).toContain('52 条待核查');
  expect(JSON.stringify(report)).toBe(original);
  const view = paperLintPresentation(report.result);
  expect(paperLintPresentation(view)).toEqual(view);
  expect(view.rule_runs[0].outcome).toBe('inconclusive');
});

it('counts four warnings plus one prerequisite notice consistently in live and exported totals', () => {
  const numeric: PaperLintRuleRun = { ...base, rule_id: 'abstract_numeric_consistency_check', outcome: 'not_applicable', findings: [],
    params: { preconditions: [{ id: 'abstract_numeric', passed: false, status: 'failed' }] } };
  const warning: PaperLintRuleRun = { ...base, rule_id: 'sjtu_rule_18', severity: 'warning', outcome: 'issues_found', params: {},
    findings: [1, 2, 3, 4].map(n => ({ finding_id: `w-${n}`, rule_id: 'sjtu_rule_18', message: `警告 ${n}` })) };
  const result = { ...fixture.result, rule_runs: [numeric, warning], summary: { ...fixture.result.summary,
    finding_count: 4, warning_finding_count: 4, info_finding_count: 0, error_finding_count: 0 } };
  const view = paperLintPresentation(result);
  expect(view.summary).toMatchObject({ finding_count: 5, warning_finding_count: 4, info_finding_count: 0, execution_warning_count: 1 });
  expect(paperLintPresentation(view)).toEqual(view);
  expect(buildExportReport({ ...fixture, result }, [], null).summary.finding_count).toBe(5);
  render(<LivePaperLintReport file={{ name: 'paper.pdf', url: '/paper.pdf' }} rules={rules} runs={[numeric, warning]} />);
  expect(screen.getByText('错误总数').closest('div')).toHaveTextContent('5');
  for (const label of ['严重 0', '警告 4', '提示 0', '规则未实现警告 1', '全部']) {
    fireEvent.click(screen.getByRole('button', { name: label, exact: true }));
    expect(screen.getByText('5 项问题')).toBeInTheDocument();
  }
});
