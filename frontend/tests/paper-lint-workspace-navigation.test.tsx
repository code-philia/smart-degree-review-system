import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PaperLintWorkspace } from '../src/components/paperLint/Workspace';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

vi.mock('../src/components/paperLint/PdfPane', () => ({
  PdfPane: ({ navigationRequest }: { navigationRequest?: number }) =>
    <div data-testid="navigation-request">{navigationRequest ?? 'missing'}</div>,
}));
vi.mock('../src/components/paperLint/FindingsPane', () => ({
  FindingsPane: ({ onFindingClick }: { onFindingClick: (key: string) => void }) =>
    <button type="button" onClick={() => onFindingClick('finding-1')}>跳到 PDF</button>,
}));

const finding: PaperLintFindingItem = {
  key: 'finding-1', index: 0,
  ruleRun: { rule_run_id: 'run-24', rule_id: 'sjtu_rule_24', severity: 'warning',
    execution_status: 'completed', outcome: 'issues_found', findings: [] },
  finding: { finding_id: 'finding-1', rule_id: 'sjtu_rule_24', message: '参考文献未引用' },
};

describe('finding selection', () => {
  it('sends a new navigation request even when the already selected problem is clicked again', () => {
    render(<PaperLintWorkspace file={{ name: 'mutant.pdf' } as File}
      findings={[finding]} rules={[]} />);
    fireEvent.click(screen.getByRole('button', { name: '跳到 PDF' }));
    fireEvent.click(screen.getByRole('button', { name: '跳到 PDF' }));
    expect(screen.getByTestId('navigation-request').textContent).toBe('2');
  });
});