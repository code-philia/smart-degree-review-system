import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { LivePaperLintReport } from '../src/components/paperLint/LivePaperLintReport';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';

vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));
const numericId = 'abstract_numeric_consistency_check';
const rules = [
  { rule_id: 'sjtu_rule_18', title: '公式引用' },
  { rule_id: 'chapter_new_page_check', title: '章标题另起一页' },
  { rule_id: numericId, title: '论点论据一致性检测' },
] as PaperLintRule[];
const finished: PaperLintRuleRun = { rule_id: 'sjtu_rule_18', rule_run_id: 'formula', severity: 'warning', execution_status: 'completed', outcome: 'issues_found',
  findings: [{ finding_id: 'one', rule_id: 'sjtu_rule_18', message: '已检测出的警告' }] };
const callbacks = { activeFindingKey: null, activeAnchorId: null, onFindingClick: vi.fn(), onAnchorClick: vi.fn() };

it.each([0, 1])('shows an explicit execution-warning statistic when the experimental rule is selected (count=%s)', count => {
  const numeric = { ...finished, rule_id: numericId, findings: [], params: { preconditions: [{ id: 'abstract_numeric', passed: false, status: 'failed' }] } };
  render(<LivePaperLintReport file={{ name: 'paper.pdf', url: '/paper.pdf' }} rules={rules}
    selectedRuleIds={['sjtu_rule_18', numericId]} runs={count ? [finished, numeric] : [finished]} />);
  expect(screen.getByText('规则未实现警告数').closest('div')).toHaveTextContent(String(count));
  expect(screen.getByText('错误总数').closest('div')).toHaveTextContent(String(1 + count));
});

it('keeps a zero execution-warning statistic without an experimental selection', () => {
  render(<LivePaperLintReport file={{ name: 'paper.pdf', url: '/paper.pdf' }} rules={rules} selectedRuleIds={['sjtu_rule_18']} runs={[finished]} />);
  expect(screen.getByText('规则未实现警告数').closest('div')).toHaveTextContent('0');
});

it.each(['全部', '严重 0', '警告 1', '提示 0'])('keeps every pending rule available alongside matching findings in a live filter (%s)', async level => {
  render(<FindingsPane {...callbacks} rules={rules} selectedRuleIds={rules.map(rule => rule.rule_id)} running
    findings={flattenPaperLintFindings({ rule_runs: [finished] })} ruleRuns={[finished]} />);
  fireEvent.click(screen.getByRole('button', { name: level, exact: true }));
  expect(screen.getByRole('combobox')).toHaveTextContent('正在检测 2');
  if (['严重 0', '提示 0'].includes(level)) {
    expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
    expect(screen.queryByText(/当前筛选未发现/)).not.toBeInTheDocument();
  }
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const menu = await screen.findByRole('listbox');
  for (const name of ['章标题另起一页', '论点论据一致性检测']) {
    expect(within(menu).getByRole('option', { name: `${name}，正在检测` })).toBeInTheDocument();
    expect(within(menu).getByRole('option', { name: `${name}，正在检测` })).not.toHaveTextContent(/正在检测\s+\d/);
  }
  expect(within(menu).queryByRole('option', { name: /^公式引用，/ }) !== null).toBe(level === '全部' || level === '警告 1');
  const pending = within(menu).getByRole('option', { name: '章标题另起一页，正在检测' });
  pending.focus(); fireEvent.keyDown(pending, { key: 'Enter' });
  expect(screen.getByRole('combobox')).toHaveTextContent('正在检测');
  expect(screen.getByRole('combobox')).not.toHaveTextContent(/正在检测\s+\d/);
  expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
});

it('stops showing loading once all pending rules complete outside the active severity', () => {
  const props = { ...callbacks, rules, selectedRuleIds: ['sjtu_rule_18', 'chapter_new_page_check'], running: true,
    findings: flattenPaperLintFindings({ rule_runs: [finished] }) };
  const { rerender } = render(<FindingsPane {...props} ruleRuns={[finished]} />);
  fireEvent.click(screen.getByRole('button', { name: '严重 0', exact: true }));
  expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
  rerender(<FindingsPane {...props} ruleRuns={[finished, { ...finished, rule_id: 'chapter_new_page_check', findings: [], outcome: 'passed' }]} />);
  expect(screen.queryByText('正在检测相关问题')).not.toBeInTheDocument();
  expect(screen.getByText('当前筛选未发现严重级别的问题')).toBeInTheDocument();
});

it('places numeric warnings before numeric information while retaining finding identities', () => {
  const run: PaperLintRuleRun = { ...finished, rule_id: numericId, findings: [], params: { numeric_results: [
    { declaration_id: 'info-1', status: 'inconclusive', reason: '待复核一' },
    { declaration_id: 'warning', status: 'inconsistent', reason: '数值矛盾' },
    { declaration_id: 'info-2', status: 'inconclusive', reason: '待复核二' },
  ] } };
  const findings = flattenPaperLintFindings({ rule_runs: [run] });
  expect(findings.map(item => item.ruleRun.severity)).toEqual(['warning', 'info', 'info']);
  expect(findings.map(item => item.key)).toEqual([`${numericId}_warning`, `${numericId}_info-1`, `${numericId}_info-2`]);
});
