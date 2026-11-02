import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { flattenPaperLintFindings, numericExecutionWarnings } from '../src/components/paperLint/model';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';

function run(): PaperLintRuleRun {
  return { rule_id: 'abstract_numeric_consistency_check', rule_run_id: 'n', severity: 'warning', execution_status: 'completed', outcome: 'issues_found', findings: [], params: {
    preconditions: [{ id: 'abstract_numeric', passed: true }],
    numeric_results: [
      { declaration_id: 'd1', status: 'inconsistent', reason: '同一指标数值矛盾', suggestion: '请核对实验数值' },
      { declaration_id: 'd2', status: 'inconclusive', reason: '统计范围不明确', suggestion: '请补充统计范围' },
      { declaration_id: 'd3', status: 'consistent', reason: '一致' },
      { declaration_id: 'd4', status: 'execution_error', reason: '请求超时' },
    ],
  } };
}
describe('numeric results in the unified report', () => {
  it('shows full prerequisite details in all levels and keeps them scoped to the selected rule', async () => {
    const numeric: PaperLintRuleRun = { ...run(), outcome: 'not_applicable', findings: [], params: {
      preconditions: [{ id: 'abstract_numeric', passed: false, status: 'failed' }],
    } };
    const formula: PaperLintRuleRun = { ...numeric, rule_id: 'sjtu_rule_18', rule_run_id: 'formula', outcome: 'issues_found', params: {},
      findings: [{ finding_id: 'f1', rule_id: 'sjtu_rule_18', message: '公式引用问题', location: null }] };
    render(<FindingsPane findings={flattenPaperLintFindings({ rule_runs: [numeric, formula] })}
      rules={[{ rule_id: numeric.rule_id, title: '论点论据一致性检测' }, { rule_id: formula.rule_id, title: '公式引用' }] as PaperLintRule[]}
      selectedRuleIds={[numeric.rule_id, formula.rule_id]} ruleRuns={[numeric, formula]}
      executionWarnings={numericExecutionWarnings(numeric)} activeFindingKey={null} activeAnchorId={null}
      onFindingClick={() => {}} onAnchorClick={() => {}} />);
    expect(screen.getByRole('heading', { name: '摘要中不存在可核验的含有数值的论点' })).toBeInTheDocument();
    expect(screen.getByText('公式引用问题')).toBeInTheDocument();
    expect(screen.getByText('2 项问题')).toBeInTheDocument();
    const select = async (title: string) => {
      fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
      const option = await screen.findByRole('option', { name: new RegExp(`^${title}，`) });
      option.focus(); fireEvent.keyDown(option, { key: 'Enter' });
    };
    await select('公式引用');
    expect(screen.queryByRole('heading', { name: '摘要中不存在可核验的含有数值的论点' })).not.toBeInTheDocument();
    await select('论点论据一致性检测');
    expect(screen.getByRole('heading', { name: '摘要中不存在可核验的含有数值的论点' })).toBeInTheDocument();
    expect(screen.getByText('符合要求的示例：')).toBeInTheDocument();
    expect(screen.queryByText('公式引用问题')).not.toBeInTheDocument();
    expect(screen.queryByTestId('rule-empty-icon')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '警告 1', exact: true }));
    expect(screen.queryByText('符合要求的示例：')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /规则未实现警告/ }));
    expect(screen.getByText('符合要求的示例：')).toBeInTheDocument();
  });
  it('shows warning and info findings, hides consistent and failed checks, and uses inline suggestions', () => {
    const findings = flattenPaperLintFindings({ rule_runs: [run()] });
    expect(findings.map(f => f.ruleRun.severity)).toEqual(['warning', 'info']);
    render(<FindingsPane findings={findings} rules={[]} activeFindingKey={null} activeAnchorId={null} onFindingClick={() => {}} onAnchorClick={() => {}} onGenerateRepairSuggestion={() => { throw new Error('unexpected generation'); }} />);
    expect(screen.getByText('请核对实验数值')).toBeTruthy();
    expect(screen.queryByText('获取修复建议')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '提示 1', exact: true }));
    expect(screen.getByText('论据不明确：统计范围不明确')).toBeTruthy();
    expect(screen.queryByText('论点与论据不一致：同一指标数值矛盾')).toBeNull();
  });
  it('counts prerequisite and technical notices in the total while keeping them outside severity counts', () => {
    const value = run();
    value.execution_status = 'error';
    value.params!.preconditions = [{ id: 'experiment_subsection', passed: false, reason: '没有对应实验章节', suggestion: '补充实验章节' }];
    const warnings = numericExecutionWarnings(value);
    expect(warnings).toHaveLength(2);
    expect(flattenPaperLintFindings({ rule_runs: [value] })).toHaveLength(0);
    render(<FindingsPane findings={[]} rules={[]} executionWarnings={warnings} activeFindingKey={null} activeAnchorId={null} onFindingClick={() => {}} onAnchorClick={() => {}} />);
    expect(screen.getByText('2 项问题')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '警告 0', exact: true })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /规则未实现警告/ }));
    expect(screen.getByText('研究贡献下不存在明确的实验章节')).toBeTruthy();
    expect(screen.getByText(/请稍后重试/)).toBeTruthy();
  });
});
