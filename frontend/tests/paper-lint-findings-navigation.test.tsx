import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

const item: PaperLintFindingItem = {
  key: 'finding-99', index: 0,
  ruleRun: { rule_run_id: 'run-24', rule_id: 'sjtu_rule_24', severity: 'warning',
    execution_status: 'completed', outcome: 'issues_found', findings: [] },
  finding: { finding_id: 'finding-99', rule_id: 'sjtu_rule_24', message: '参考文献 [4] 未在全文引用',
    location: { type: 'pdf_bbox', page_number: 99,
      bounding_rect: { x1: 85, y1: 247, x2: 517, y2: 263, width: 595, height: 842, page_number: 99 },
      rects: [] } },
};

describe('PDF issue card', () => {
  it('offers an explicit page-jump control for a located issue', () => {
    const onFindingClick = vi.fn();
    render(<FindingsPane findings={[item]} rules={[]} activeFindingKey="finding-99"
      activeAnchorId={null} onFindingClick={onFindingClick} onAnchorClick={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '跳到 PDF 第 99 页' }));
    expect(onFindingClick).toHaveBeenCalledWith('finding-99');
  });
});