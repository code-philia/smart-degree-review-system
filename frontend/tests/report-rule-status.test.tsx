import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { RuleFilter, type RuleFilterOption } from '../src/components/paperLint/RuleFilter';
import { genericExecutionWarnings } from '../src/components/paperLint/model';

const rules = [
  { rule_id: 'sjtu_rule_18', title: '已完成检查' },
  { rule_id: 'typo_detection_check', title: '待完成检查' },
] as PaperLintRule[];
const completed: PaperLintRuleRun = { rule_id: 'sjtu_rule_18', rule_run_id: 'done', severity: 'warning',
  execution_status: 'completed', outcome: 'passed', findings: [] };
const props = { rules, selectedRuleIds: rules.map(rule => rule.rule_id), findings: [],
  activeFindingKey: null, activeAnchorId: null, onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
async function menu() {
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  return screen.findByRole('listbox');
}

it.each([false, true])('keeps the execution-warning filter selectable with zero warnings (live=%s)', running => {
  render(<FindingsPane {...props} running={running} ruleRuns={[completed]} />);
  fireEvent.click(screen.getByRole('button', { name: '规则未实现警告 0', exact: true }));
  expect(screen.getByRole('button', { name: '规则未实现警告 0', exact: true })).toHaveAttribute('aria-pressed', 'true');
});

it.each([false, true])('places blue information and review after warnings and before pending or clean rules (live=%s)', async running => {
  const option = (id: string, status: RuleFilterOption['status'], counts = { error: 0, warning: 0, info: 0 }): RuleFilterOption => ({
    id, title: id, status, counts, count: counts.error + counts.warning + counts.info,
  });
  const options = [option('蓝色提示', 'completed', { error: 0, warning: 0, info: 126 }),
    option('待核查', 'needs_review'), option('没有问题', 'completed'),
    ...(running ? [option('正在检测', 'running')] : []),
    option('规则未完成', 'execution_warning'), option('普通警告', 'completed', { error: 0, warning: 1, info: 0 }),
    option('严重问题', 'completed', { error: 1, warning: 0, info: 0 })];
  render(<RuleFilter options={options} value="all" onValueChange={vi.fn()} totalCount={128} />);
  const list = await menu();
  expect(within(list).getAllByRole('option').map(row => row.textContent?.split('，')[0])).toEqual([
    '全部检查项', '严重问题', '普通警告', '规则未完成', '蓝色提示', '待核查', ...(running ? ['正在检测'] : []), '没有问题',
  ]);
});

it.each([0, 1])('keeps pending rules selectable and labelled as running in the execution category (warnings=%s)', async warningCount => {
  const run = { ...completed, execution_status: warningCount ? 'unsupported' as const : 'completed' as const,
    outcome: warningCount ? 'inconclusive' as const : 'passed' as const, message: '缺少检测前置条件' };
  const { rerender } = render(<FindingsPane {...props} running ruleRuns={[run]} executionWarnings={genericExecutionWarnings([run])} />);
  fireEvent.click(screen.getByRole('button', { name: `规则未实现警告 ${warningCount}`, exact: true }));
  expect(screen.getByRole('combobox')).toHaveTextContent('正在检测 1');
  const list = await menu();
  expect(within(list).getAllByRole('option')).toHaveLength(warningCount + 2);
  const pending = within(list).getByRole('option', { name: '待完成检查，正在检测' });
  expect(pending).toHaveTextContent('正在检测');
  act(() => { pending.focus(); fireEvent.keyDown(pending, { key: 'Enter' }); });
  expect(screen.getByText('正在检测相关问题')).toBeInTheDocument();
  expect(screen.queryByText('当前筛选未发现规则未实现警告')).not.toBeInTheDocument();
  rerender(<FindingsPane {...props} running ruleRuns={[run, { ...completed, rule_id: 'typo_detection_check' }]}
    executionWarnings={genericExecutionWarnings([run])} />);
  expect(screen.getByRole('combobox')).toHaveTextContent('全部检查项');
  expect(screen.queryByText('正在检测相关问题')).not.toBeInTheDocument();
  if (!warningCount) expect(screen.getByText('当前筛选未发现规则未实现警告')).toBeInTheDocument();
  const doneMenu = await menu();
  expect(within(doneMenu).queryByRole('option', { name: /^待完成检查，/ })).not.toBeInTheDocument();
});
