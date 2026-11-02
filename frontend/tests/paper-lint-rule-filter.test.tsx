import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
import { RuleFilter, type RuleFilterOption } from '../src/components/paperLint/RuleFilter';

const rules = [
  { rule_id: 'sjtu_rule_18', title: '正文公式引用目标缺失' },
  { rule_id: 'chapter_new_page_check', title: '章标题另起一页' },
  { rule_id: 'typo_detection_check', title: '正文错别字检测' },
  { rule_id: 'unselected', title: '未选择规则' },
] as PaperLintRule[];
const selectedRuleIds = rules.slice(0, 3).map(rule => rule.rule_id);
const zero: PaperLintRuleRun = { rule_id: 'chapter_new_page_check', rule_run_id: 'chapter', severity: 'warning',
  execution_status: 'completed', outcome: 'passed', findings: [] };
const issues: PaperLintRuleRun = { ...zero, rule_id: 'sjtu_rule_18', rule_run_id: 'formula', outcome: 'issues_found',
  findings: [1, 2].map(n => ({ finding_id: `formula-${n}`, rule_id: 'sjtu_rule_18', message: `公式引用问题 ${n}`, location: null })) };
const props = { rules, selectedRuleIds, activeFindingKey: null, activeAnchorId: null,
  onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
async function openMenu() {
  fireEvent.keyDown(screen.getByRole('combobox', { name: '按检查项筛选' }), { key: 'ArrowDown' });
  return screen.findByRole('listbox');
}
async function selectRule(title: string) {
  const list = await openMenu();
  const option = within(list).getByRole('option', { name: new RegExp(`^${title}，`) });
  option.focus(); fireEvent.keyDown(option, { key: 'Enter' });
}

describe('clear report rule selector', () => {
  it('shows severity totals and puts rules with findings first in the all-level menu', async () => {
    render(<FindingsPane {...props} running findings={flattenPaperLintFindings({ rule_runs: [issues, zero] })} ruleRuns={[issues, zero]} />);
    expect(screen.getByRole('heading', { name: '检测结果' })).toBeInTheDocument();
    expect(screen.getAllByRole('combobox')).toHaveLength(1);
    expect(screen.getByRole('combobox')).toHaveTextContent('正在检测 1');
    for (const name of ['全部', '严重 0', '警告 2', '提示 0']) expect(screen.getByRole('button', { name, exact: true })).toBeInTheDocument();
    const list = await openMenu();
    expect(within(list).getByRole('option', { name: /^正文公式引用目标缺失，问题总数 2 处/ })).toHaveTextContent('2');
    expect(within(list).getByRole('option', { name: '章标题另起一页，问题总数 0 处' })).toBeVisible();
    expect(within(list).getByRole('option', { name: '正文错别字检测，正在检测' })).toBeVisible();
    expect(within(list).queryByText('未选择规则')).not.toBeInTheDocument();
    expect(within(list).queryByText(/规则优先展示|数量按级别/)).not.toBeInTheDocument();
    expect(within(list).getAllByRole('option')[1]).toHaveTextContent('正文公式引用目标缺失');
  });

  it('changes the selected pending rule to a completed zero-issue state without losing the selection', async () => {
    const findings = flattenPaperLintFindings({ rule_runs: [issues] });
    const { rerender } = render(<FindingsPane {...props} running findings={findings} ruleRuns={[issues]} />);
    expect(screen.getByRole('combobox')).toHaveTextContent('正在检测 2');
    await selectRule('章标题另起一页');
    expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
    rerender(<FindingsPane {...props} running findings={findings} ruleRuns={[issues, zero]} />);
    expect(screen.getByRole('combobox')).toHaveTextContent('章标题另起一页');
    expect(screen.getByText('本规则未检测出问题')).toBeInTheDocument();
    expect(screen.queryByText('正在检测相关问题')).not.toBeInTheDocument();
    expect(screen.getByTestId('rule-empty-icon')).toHaveClass('text-success-600');
  });

  it('shows the selected completed rule findings while other rules are pending', async () => {
    render(<FindingsPane {...props} running findings={flattenPaperLintFindings({ rule_runs: [issues] })} ruleRuns={[issues]} />);
    await selectRule('正文公式引用目标缺失');
    expect(screen.getByText('公式引用问题 1')).toBeInTheDocument();
    expect(screen.getByText('公式引用问题 2')).toBeInTheDocument();
  });

  it.each([
    ['error', 'inconclusive', '检测失败', '本规则检测失败'],
    ['completed', 'inconclusive', '待核查', '本规则暂无法判定'],
    ['completed', 'not_applicable', '不适用', '本规则不适用'],
  ] as const)('keeps %s/%s separate from a successful zero count', async (execution_status, outcome, label, title) => {
    const run = { ...zero, execution_status, outcome, message: '原文证据不足或检测未完成' };
    render(<FindingsPane {...props} findings={[]} ruleRuns={[run]} />);
    const list = await openMenu();
    const option = within(list).getByRole('option', { name: `章标题另起一页，${label}` });
    expect(within(option).queryByText('0处')).not.toBeInTheDocument();
    option.focus(); fireEvent.keyDown(option, { key: 'Enter' });
    expect(screen.getByText(title)).toBeInTheDocument();
    expect(screen.queryByTestId('rule-empty-icon')).not.toBeInTheDocument();
  });

  it('resets an excluded rule when changing severity and explains an empty severity filter', async () => {
    render(<FindingsPane {...props} findings={flattenPaperLintFindings({ rule_runs: [issues, zero] })} ruleRuns={[issues, zero]} />);
    await selectRule('正文公式引用目标缺失');
    fireEvent.click(screen.getByRole('button', { name: '严重 0', exact: true }));
    expect(screen.getByText('当前筛选未发现严重级别的问题')).toBeInTheDocument();
    expect(screen.getByText('当前报告共发现 2 处问题，分布在其他级别。')).toBeInTheDocument();
    expect(screen.queryByTestId('rule-empty-icon')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看全部级别' }));
    expect(screen.getByText('公式引用问题 1')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveTextContent('全部检查项');
  });

  it('supports keyboard navigation and restores trigger focus', async () => {
    render(<FindingsPane {...props} running findings={[]} ruleRuns={[]} />);
    await openMenu(); fireEvent.keyDown(screen.getByRole('listbox'), { key: 'End' });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('option', { name: '正文错别字检测，正在检测' })));
    fireEvent.keyDown(document.activeElement!, { key: 'Enter' });
    expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole('combobox')));
  });

  it('retains a nonzero count together with an inconclusive status', async () => {
    const run = { ...issues, outcome: 'inconclusive' as const };
    render(<FindingsPane {...props} findings={flattenPaperLintFindings({ rule_runs: [run] })} ruleRuns={[run]} />);
    const list = await openMenu();
    expect(within(list).getByRole('option', { name: '正文公式引用目标缺失，已发现 2 处问题，待核查' })).toBeInTheDocument();
  });

  it('filters completed rules by severity while keeping pending rules available', async () => {
    const errorRun = { ...issues, severity: 'error' as const };
    render(<FindingsPane {...props} running findings={flattenPaperLintFindings({ rule_runs: [errorRun, zero] })} ruleRuns={[errorRun, zero]} />);
    fireEvent.click(screen.getByRole('button', { name: '警告 0', exact: true }));
    const list = await openMenu();
    expect(within(list).queryByRole('option', { name: /^正文公式引用目标缺失，/ })).not.toBeInTheDocument();
    expect(within(list).queryByRole('option', { name: /^章标题另起一页，/ })).not.toBeInTheDocument();
    const pendingOption = within(list).getByRole('option', { name: '正文错别字检测，正在检测' });
    pendingOption.focus(); fireEvent.keyDown(pendingOption, { key: 'Enter' });
    expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
  });

  it('shows separate severity badges for a rule containing multiple finding levels', async () => {
    const mixed = { ...issues, findings: issues.findings.map((finding, index) => ({ ...finding, severity: index ? 'info' : 'error' })) } as PaperLintRuleRun;
    render(<FindingsPane {...props} findings={flattenPaperLintFindings({ rule_runs: [mixed, zero] })} ruleRuns={[mixed, zero]} />);
    const list = await openMenu();
    const option = within(list).getByRole('option', { name: /^正文公式引用目标缺失，问题总数 2 处，严重 1 处，提示 1 处/ });
    expect(option.querySelector('[data-severity="error"]')).toHaveTextContent('1');
    expect(option.querySelector('[data-severity="info"]')).toHaveTextContent('1');
  });

  it('orders live findings, review states, running checks and clean results, then reorders new findings', async () => {
    const option = (id: string, status: RuleFilterOption['status'], count = 0): RuleFilterOption => ({
      id, title: id, status, count, counts: { error: 0, warning: count, info: 0 },
    });
    const options = [option('clean', 'completed'), option('pending', 'running'), option('review', 'needs_review'), option('failed', 'error'), option('issues', 'completed', 1)];
    const { rerender } = render(<RuleFilter options={options} value="review" onValueChange={vi.fn()} totalCount={1} />);
    let list = await openMenu();
    expect(within(list).getAllByRole('option').map(row => row.textContent?.split('，')[0])).toEqual(['全部检查项', 'issues', 'review', 'failed', 'pending', 'clean']);
    expect(within(list).getByText('5 条规则')).toBeInTheDocument();
    fireEvent.keyDown(list, { key: 'Escape' });
    rerender(<RuleFilter options={options.map(row => row.id === 'pending' ? option('pending', 'completed', 2) : row)} value="review" onValueChange={vi.fn()} totalCount={3} />);
    list = await openMenu();
    expect(within(list).getAllByRole('option').map(row => row.textContent?.split('，')[0])).toEqual(['全部检查项', 'pending', 'issues', 'review', 'failed', 'clean']);
    expect(within(list).getByRole('option', { name: 'review，待核查' })).toHaveAttribute('data-state', 'checked');
  });

  it.each([false, true])('labels failed experimental prerequisites and sorts them before clean rules (live=%s)', async running => {
    const numeric = { ...zero, rule_id: 'abstract_numeric_consistency_check', rule_run_id: 'numeric', outcome: 'not_applicable' as const,
      message: '摘要中未发现可核验的数值声明，已跳过数值一致性检测。',
      params: { preconditions: [{ id: 'abstract_numeric', passed: false, status: 'failed' }] } };
    render(<FindingsPane {...props} rules={[...rules, { rule_id: numeric.rule_id, title: '论点论据一致性检测' } as PaperLintRule]}
      selectedRuleIds={[issues.rule_id, zero.rule_id, numeric.rule_id]} running={running}
      findings={flattenPaperLintFindings({ rule_runs: [issues, zero, numeric] })} ruleRuns={[issues, zero, numeric]} />);
    const list = await openMenu();
    expect(within(list).getAllByRole('option').map(row => row.textContent?.split('，')[0])).toEqual(['全部检查项', '正文公式引用目标缺失', '论点论据一致性检测', '章标题另起一页']);
    const option = within(list).getByRole('option', { name: '论点论据一致性检测，规则未实现警告' });
    expect(option).not.toHaveTextContent('不适用');
    option.focus(); fireEvent.keyDown(option, { key: 'Enter' });
    expect(screen.getByRole('combobox')).toHaveTextContent('规则未实现警告');
    expect(screen.getByText('规则未实现警告', { selector: 'p' })).toBeInTheDocument();
    expect(screen.getByText(numeric.message)).toBeInTheDocument();
    expect(screen.queryByTestId('rule-empty-icon')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '严重 0', exact: true }));
    expect(screen.getByRole('combobox')).toHaveTextContent('论点论据一致性检测');
    expect(screen.getByRole('combobox')).toHaveTextContent('规则未实现警告');
  });

  it('keeps non-applicable rules above clean rules and pending checks', async () => {
    const options: RuleFilterOption[] = [
      { id: 'clean', title: '无问题规则', count: 0, counts: { error: 0, warning: 0, info: 0 }, status: 'completed' },
      { id: 'na', title: '不适用规则', count: 0, counts: { error: 0, warning: 0, info: 0 }, status: 'not_applicable' },
      { id: 'pending', title: '检测中规则', count: 0, counts: { error: 0, warning: 0, info: 0 }, status: 'running' },
    ];
    render(<RuleFilter options={options} value="all" onValueChange={vi.fn()} totalCount={0} />);
    const list = await openMenu();
    expect(within(list).getAllByRole('option').map(row => row.textContent?.split('，')[0])).toEqual(['全部检查项', '不适用规则', '检测中规则', '无问题规则']);
  });

  it('keeps review states above clean rules in saved reports', async () => {
    const options: RuleFilterOption[] = [
      { id: 'clean', title: '无问题规则', count: 0, counts: { error: 0, warning: 0, info: 0 }, status: 'completed' },
      { id: 'review', title: '待核查规则', count: 0, counts: { error: 0, warning: 0, info: 0 }, status: 'needs_review' },
    ];
    render(<RuleFilter options={options} value="all" onValueChange={vi.fn()} totalCount={0} />);
    const list = await openMenu();
    expect(within(list).getAllByRole('option').map(row => row.textContent?.split('，')[0])).toEqual(['全部检查项', '待核查规则', '无问题规则']);
  });
});
