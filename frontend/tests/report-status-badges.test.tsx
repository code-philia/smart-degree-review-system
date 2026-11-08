import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { RuleFilter, type RuleFilterOption } from '../src/components/paperLint/RuleFilter';
import { flattenPaperLintFindings, genericExecutionWarnings, numericExecutionWarnings } from '../src/components/paperLint/model';

const numericId = 'abstract_numeric_consistency_check';
const referenceId = 'sjtu_rule_32';
const rules = [
  { rule_id: numericId, title: '数值核验' }, { rule_id: referenceId, title: '引用核验' },
  { rule_id: 'typo_detection_check', title: '错别字检测' }, { rule_id: 'sjtu_rule_18', title: '公式检测' },
] as PaperLintRule[];
const completed: PaperLintRuleRun = { rule_id: 'sjtu_rule_18', rule_run_id: 'done', severity: 'warning',
  execution_status: 'completed', outcome: 'passed', findings: [] };
const numeric: PaperLintRuleRun = { ...completed, rule_id: numericId, params: { preconditions: [
  { id: 'abstract_numeric', passed: false, status: 'failed' },
  { id: 'contribution_mapping', passed: false, status: 'failed' },
  { id: 'experiment_subsection', passed: false, status: 'failed' },
  { id: 'ignored', passed: false, status: 'skipped' },
] } };
const reference: PaperLintRuleRun = { ...completed, rule_id: referenceId, severity: 'info', outcome: 'inconclusive',
  params: { reference_resources_unavailable: true }, message: '部分引用未完成核验。' };
const common = { rules, selectedRuleIds: rules.map(rule => rule.rule_id), activeFindingKey: null, activeAnchorId: null,
  onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
function pane(runs: PaperLintRuleRun[], running: boolean) {
  return <FindingsPane {...common} running={running} ruleRuns={runs} findings={flattenPaperLintFindings({rule_runs:runs})}
    executionWarnings={[...numericExecutionWarnings(runs.find(run=>run.rule_id===numericId)),...genericExecutionWarnings(runs)]} />;
}
async function menu() {
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  return screen.findByRole('listbox');
}


it.each(['all','execution'])('counts the summary while keeping individual purple badges unnumbered (%s)',category=>{
  render(pane([completed,numeric,reference],true));
  if(category==='execution') fireEvent.click(screen.getByRole('button',{name:'规则未实现警告 4',exact:true}));
  const trigger=screen.getByRole('combobox');
  const badge=within(trigger).getByTitle('规则未实现警告 4 项');
  expect(badge).toHaveTextContent(/^4$/);
  expect(trigger).not.toHaveTextContent('待核查');
  expect(trigger).toHaveTextContent('正在检测 1');
});

it.each(['inconclusive','passed','issues_found'] as const)('shows one plain purple badge for a reference warning (%s)',async outcome=>{
  const findings=outcome==='issues_found'?[{finding_id:'ref',rule_id:referenceId,message:'有依据的引用疑点'}]:[];
  render(pane([{...reference,outcome,findings}],false));
  fireEvent.click(screen.getByRole('button',{name:'规则未实现警告 1',exact:true}));
  const list=await menu();
  const option=within(list).getByRole('option',{name:/^引用核验，/});
  const badge=within(option).getByTitle('规则未实现警告');
  expect(badge).toHaveTextContent('规则未实现警告');
  expect(badge).not.toHaveTextContent(/\d/);
  expect(within(option).queryByText('待核查',{exact:true})).not.toBeInTheDocument();
  act(()=>{option.focus();fireEvent.keyDown(option,{key:'Enter'});});
  const trigger=screen.getByRole('combobox');
  expect(within(trigger).getByTitle('规则未实现警告 1 项')).toHaveTextContent(/^1$/);
  expect(within(trigger).queryByText('待核查',{exact:true})).not.toBeInTheDocument();
  expect(within(trigger).queryByText('0')).not.toBeInTheDocument();
});

it('keeps multiple warning entries in the category total while using one plain rule badge',async()=>{
  render(pane([numeric],false));
  fireEvent.click(screen.getByRole('button',{name:'规则未实现警告 3',exact:true}));
  const list=await menu();
  const option=within(list).getByRole('option',{name:/^数值核验，/});
  expect(within(option).getAllByTitle('规则未实现警告')).toHaveLength(1);
  expect(within(option).getByTitle('规则未实现警告')).not.toHaveTextContent(/\d/);
});

it('removes warning and running badges once all corresponding rules complete',()=>{
  const {rerender}=render(pane([completed,numeric,reference],true));
  const trigger=screen.getByRole('combobox');
  expect(within(trigger).getByTitle('规则未实现警告 4 项')).toBeInTheDocument();
  rerender(pane(rules.map(rule=>({...completed,rule_id:rule.rule_id})),false));
  expect(within(trigger).queryByTitle(/规则未实现警告/)).not.toBeInTheDocument();
  expect(trigger).not.toHaveTextContent('待核查');
  expect(trigger).not.toHaveTextContent('正在检测');
  expect(within(trigger).getByText('0')).toBeInTheDocument();
});

it('summarizes review only for a visible review row and keeps purple rows above blue rows',async()=>{
  const options:RuleFilterOption[]=[
    {id:'review',title:'独立待核查规则',count:0,counts:{error:0,warning:0,info:0},status:'needs_review'},
    {id:'warning',title:'未完成检测',count:0,counts:{error:0,warning:0,info:0},status:'needs_review',executionWarningCount:2},
  ];
  render(<RuleFilter options={options} value="all" onValueChange={vi.fn()} totalCount={2}/>);
  const trigger=screen.getByRole('combobox');
  expect(within(trigger).getByTitle('规则未实现警告 2 项')).toHaveTextContent(/^2$/);
  expect(trigger).toHaveTextContent('待核查 1');
  const list=await menu();
  expect(within(list).getAllByRole('option').map(row=>row.textContent?.split('，')[0])).toEqual(['全部检查项','未完成检测','独立待核查规则']);
  const warning=within(list).getByRole('option',{name:/^未完成检测，/});
  expect(within(warning).getByTitle('规则未实现警告')).toBeInTheDocument();
  expect(within(warning).queryByText('待核查',{exact:true})).not.toBeInTheDocument();
  expect(within(list).getByRole('option',{name:/^独立待核查规则，/})).toHaveTextContent('待核查');
});


it.each(['all', 'mixed'])('keeps blue finding badges after execution warnings in the trigger and rule row (selected=%s)', async value => {
  const options: RuleFilterOption[] = [{
    id: 'mixed', title: '混合结果', status: 'completed', count: 3,
    counts: { error: 1, warning: 1, info: 1 }, executionWarningCount: 1,
  }];
  render(<RuleFilter options={options} value={value} onValueChange={vi.fn()} totalCount={4} />);
  const order = (element: HTMLElement) => Array.from(element.querySelectorAll('[data-severity]'))
    .map(badge => badge.getAttribute('data-severity'));
  expect(order(screen.getByRole('combobox'))).toEqual(['error', 'warning', 'execution', 'info']);
  const list = await menu();
  const option = within(list).getByRole('option', { name: /^混合结果，/ });
  expect(order(option)).toEqual(['error', 'warning', 'execution', 'info']);
});
