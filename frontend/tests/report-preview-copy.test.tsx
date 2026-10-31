import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
import type { PaperLintRule } from '../src/api/paperLint';

const item = {
  key: 'f',
  index: 0,
  finding: {
    finding_id: 'f',
    rule_id: 'sjtu_rule_15',
    message: '请核对公式引用',
    location: { type: 'pdf_page', page_number: 42 },
  },
  ruleRun: {
    rule_run_id: 'r',
    rule_id: 'sjtu_rule_15',
    severity: 'warning',
    outcome: 'issues_found',
    execution_status: 'completed',
    findings: [],
  },
} as PaperLintFindingItem;
const rules = [
  { rule_id: 'sjtu_rule_11', title: '标点' },
  { rule_id: 'sjtu_rule_15', title: '公式引用' },
] as PaperLintRule[];
it('shows the stable catalog rule number and printed page while retaining the original finding jump', () => {
  const click = vi.fn();
  render(
    <FindingsPane
      findings={[item]}
      rules={rules}
      activeFindingKey={null}
      activeAnchorId={null}
      onFindingClick={click}
      onAnchorClick={vi.fn()}
      pageLabels={{ 42: '33' }}
    />,
  );
  expect(screen.getByRole('heading', { name: '检测错误总数' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '规则 2：公式引用' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '跳到第 33 页' }));
  expect(click).toHaveBeenCalledWith('f');
  expect(screen.getByText('第 33 页')).toHaveAttribute('title', 'PDF 第 42 页');
});
it('uses the requested two-line empty result with an honest reference-only caveat', () => {
  render(
    <FindingsPane
      findings={[]}
      rules={rules}
      activeFindingKey={null}
      activeAnchorId={null}
      onFindingClick={vi.fn()}
      onAnchorClick={vi.fn()}
    />,
  );
  expect(screen.getByText('未检测出问题')).toBeInTheDocument();
  expect(
    screen.getByText('基于当前规范性检测规则，证据不足的内容仍可能无法判定，检测结果仅供参考'),
  ).toBeInTheDocument();
});
