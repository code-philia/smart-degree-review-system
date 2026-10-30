import { afterEach, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { NumericReviewDetails } from '../src/components/paperLint/NumericReviewDetails';
import { THIRTY_RULE_IDS } from '../src/utils/paperLintRuleGroups';
import type { PaperLintRuleRun } from '../src/api/paperLint';
afterEach(cleanup);
const run: PaperLintRuleRun = { rule_id: 'abstract_numeric_consistency_check', rule_run_id: 'r', severity: 'warning', outcome: 'inconclusive', execution_status: 'completed', findings: [], params: {
  preconditions: [{ id: 'experiment_subsection', passed: false, reason: '缺少下级实验子章节', suggestion: '请在研究章节下组织实验' }],
  numeric_results: [{ declaration_id: 'd1', declaration: { text: '准确率92.5%', contribution_id: 'c1' }, status: 'inconclusive', reason: '证据不足', suggestion: '请核对原始数据', evidence: [{ quote: 'Accuracy89.3%', page: 8 }] }],
} };
it('shows prerequisites, complete evidence, rationale and correction guidance', () => {
  render(<NumericReviewDetails run={run} pdfUrl="/private.pdf" />);
  expect(screen.getByText('缺少下级实验子章节')).toBeTruthy();
  expect(screen.getByText('无法确定')).toBeTruthy();
  expect(screen.getByText('判断依据：证据不足')).toBeTruthy();
  expect(screen.getByRole('link', { name: '查看 PDF 第 8 页' }).getAttribute('href')).toBe('/private.pdf#page=8');
});
it('keeps numeric reports visible in shared history and does not leak details into ordinary rules', () => {
  expect(THIRTY_RULE_IDS.has(run.rule_id)).toBe(true);
  render(<NumericReviewDetails run={{ ...run, rule_id: 'sjtu_rule_31' }} />);
  expect(screen.queryByTestId('numeric-review-details')).toBeNull();
});
