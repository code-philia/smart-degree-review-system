import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { PaperLintRuleRun } from '../src/api/paperLint';
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
  it('keeps prerequisite and technical failures outside the issue total', () => {
    const value = run();
    value.execution_status = 'error';
    value.params!.preconditions = [{ id: 'experiment_subsection', passed: false, reason: '没有对应实验章节', suggestion: '补充实验章节' }];
    const warnings = numericExecutionWarnings(value);
    expect(warnings).toHaveLength(2);
    expect(flattenPaperLintFindings({ rule_runs: [value] })).toHaveLength(0);
    render(<FindingsPane findings={[]} rules={[]} executionWarnings={warnings} activeFindingKey={null} activeAnchorId={null} onFindingClick={() => {}} onAnchorClick={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /规则未实现警告/ }));
    expect(screen.getByText('研究贡献下不存在明确的实验章节')).toBeTruthy();
    expect(screen.getByText(/请稍后重试/)).toBeTruthy();
  });
});
