import { render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings, genericExecutionWarnings, paperLintPresentation } from '../src/components/paperLint/model';
import { fixture } from './fixtures/reportExport';

const id = 'bilingual_abstract_consistency_check';
it.each([false, true])('keeps evidence validation notices separate from rule failures (valid finding=%s)', valid => {
  const run: PaperLintRuleRun = {
    rule_id: id, rule_run_id: 'abstract-partial', severity: 'warning', execution_status: 'completed',
    outcome: valid ? 'issues_found' : 'inconclusive',
    message: '摘要对照已完成，部分候选的证据暂未核实。已保留核实通过的结果；可稍后重新检测。',
    params: { validation_incomplete: true, validation_diagnostics: [{ reason: 'invalid source evidence' }] },
    findings: valid ? [{ finding_id: 'verified', rule_id: id, message: '英文摘要遗漏了独立研究结论。' }] : [],
  };
  const warnings = genericExecutionWarnings([run]);
  expect(warnings).toEqual([]);
  const result = paperLintPresentation({ ...fixture.result, rule_runs: [run] });
  expect(result.summary.execution_warning_count).toBe(0);
  expect(result.summary.finding_count).toBe(valid ? 1 : 0);
  render(<FindingsPane rules={[{ rule_id: id, title: '中英文摘要内容一致性' }]} selectedRuleIds={[id]}
    ruleRuns={[run]} findings={flattenPaperLintFindings(result)} executionWarnings={warnings}
    activeFindingKey={null} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
  expect(screen.getByRole('status')).toHaveTextContent('部分候选的证据暂未核实');
  expect(screen.queryByText(/invalid source evidence/)).not.toBeInTheDocument();
  expect(screen.queryByText('本规则未检测出问题')).not.toBeInTheDocument();
  if (valid) expect(screen.getByText('英文摘要遗漏了独立研究结论。')).toBeInTheDocument();
  expect(genericExecutionWarnings([{ ...run, execution_status: 'error' }])).toHaveLength(1);
});
