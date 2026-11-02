import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { PaperLintWorkspace } from '../src/components/paperLint/Workspace';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));
vi.mock('../src/components/paperLint/NumericReviewDetails', () => ({ NumericReviewDetails: () => <div>数值核验依据</div> }));

it('retains handled marks in the unified findings pane for numeric reports', () => {
  const item: PaperLintFindingItem = { key: 'one', index: 0,
    ruleRun: { rule_id: 'sjtu_rule_24', rule_run_id: 'run', severity: 'warning',
      execution_status: 'completed', outcome: 'issues_found', findings: [] },
    finding: { finding_id: 'one', rule_id: 'sjtu_rule_24', message: '参考文献未引用', location: null },
  };
  render(<PaperLintWorkspace file={{ name: 'mixed.pdf' } as File} findings={[item]} rules={[]}
    numericReviewRun={{ ...item.ruleRun, rule_id: 'abstract_numeric_consistency_check' }} />);
  fireEvent.click(screen.getByRole('button', { name: '标记为已处理' }));
  expect(screen.getByText('已标记为本次已处理')).toBeVisible();
  expect(screen.getByText('已标记为本次已处理')).toBeVisible();
  expect(screen.getByRole('button', { name: '取消已处理标记' })).toBeVisible();
});


it.each([
  [['sjtu_rule_24'], ['规范检测问题']],
  [['abstract_numeric_consistency_check'], ['论文逻辑审查']],
  [['sjtu_rule_24', 'abstract_numeric_consistency_check'], ['规范检测问题', '论文逻辑审查']],
])('shows categories from the saved selection even when there are no alarms (%s)', (ids, names) => {
  const allRules = [
    { rule_id: 'sjtu_rule_24', title: '参考文献引用' },
    { rule_id: 'typo_detection_check', title: '未选择的错别字规则' },
    { rule_id: 'abstract_numeric_consistency_check', title: '论点论据一致性检测' },
  ];
  render(<PaperLintWorkspace file={{ name: 'regular.pdf' } as File} findings={[]} rules={allRules as never} selectedRuleIds={ids}
    numericReviewRun={ids.includes('abstract_numeric_consistency_check') ? {
      rule_id: 'abstract_numeric_consistency_check', rule_run_id: 'passed', severity: 'warning',
      execution_status: 'completed', outcome: 'passed', findings: [],
    } : undefined} />);
  expect(screen.queryAllByRole('tab')).toHaveLength(0);
  const options = Array.from(screen.getByRole('combobox', { name: '按检查项筛选' }).querySelectorAll('option'));
  expect(options.map(option => option.value)).toEqual(expect.arrayContaining(['all', ...ids]));
  expect(options.map(option => option.value)).not.toContain('typo_detection_check');
});
