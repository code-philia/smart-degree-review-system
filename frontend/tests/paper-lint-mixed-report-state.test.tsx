import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { PaperLintWorkspace } from '../src/components/paperLint/Workspace';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));
vi.mock('../src/components/paperLint/NumericReviewDetails', () => ({ NumericReviewDetails: () => <div>数值核验依据</div> }));

it('retains handled marks in the actual findings pane across numeric tab switches', () => {
  const item: PaperLintFindingItem = { key: 'one', index: 0,
    ruleRun: { rule_id: 'sjtu_rule_24', rule_run_id: 'run', severity: 'warning',
      execution_status: 'completed', outcome: 'issues_found', findings: [] },
    finding: { finding_id: 'one', rule_id: 'sjtu_rule_24', message: '参考文献未引用', location: null },
  };
  render(<PaperLintWorkspace file={{ name: 'mixed.pdf' } as File} findings={[item]} rules={[]}
    numericReviewRun={{ ...item.ruleRun, rule_id: 'abstract_numeric_consistency_check' }} />);
  fireEvent.click(screen.getByRole('button', { name: '标记为已处理' }));
  expect(screen.getByText('已标记为本次已处理')).toBeVisible();
  fireEvent.click(screen.getByRole('tab', { name: '论文逻辑审查' }));
  expect(screen.getByText('数值核验依据')).toBeVisible();
  fireEvent.click(screen.getByRole('tab', { name: '规范检测问题' }));
  expect(screen.getByText('已标记为本次已处理')).toBeVisible();
  expect(screen.getByRole('button', { name: '取消已处理标记' })).toBeVisible();
});
