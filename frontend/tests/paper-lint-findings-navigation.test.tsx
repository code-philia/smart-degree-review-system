import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

const item: PaperLintFindingItem = {
  key: 'finding-99',
  index: 0,
  ruleRun: {
    rule_run_id: 'run-24',
    rule_id: 'sjtu_rule_24',
    severity: 'warning',
    execution_status: 'completed',
    outcome: 'issues_found',
    findings: [],
  },
  finding: {
    finding_id: 'finding-99',
    rule_id: 'sjtu_rule_24',
    message: '参考文献 [4] 未在全文引用',
    location: {
      type: 'pdf_bbox',
      page_number: 99,
      bounding_rect: { x1: 85, y1: 247, x2: 517, y2: 263, width: 595, height: 842, page_number: 99 },
      rects: [],
    },
  },
};

describe('PDF issue card', () => {
  it('offers an explicit page-jump control for a located issue', () => {
    const onFindingClick = vi.fn();
    render(
      <FindingsPane
        findings={[item]}
        rules={[]}
        activeFindingKey="finding-99"
        activeAnchorId={null}
        onFindingClick={onFindingClick}
        onAnchorClick={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: '跳到 PDF 第 99 页' }));
    expect(onFindingClick).toHaveBeenCalledWith('finding-99');
  });
});
describe('PDF rule filter order', () => {
  it('lists numbered checks numerically despite out-of-order input', () => {
    const entries = [15, 11, 2].map((number) => ({
      ...item,
      key: 'finding-' + number,
      ruleRun: { ...item.ruleRun, rule_id: 'sjtu_rule_' + number },
      finding: { ...item.finding, finding_id: 'finding-' + number, rule_id: 'sjtu_rule_' + number },
    }));
    const rules = [15, 11, 2].map((number) => ({ rule_id: 'sjtu_rule_' + number, title: '规则 ' + number }));
    render(
      <FindingsPane
        findings={entries}
        rules={rules as never}
        activeFindingKey={null}
        activeAnchorId={null}
        onFindingClick={vi.fn()}
        onAnchorClick={vi.fn()}
      />,
    );
    expect(
      Array.from(screen.getByRole('combobox', { name: '按检查项筛选' }).querySelectorAll('option')).map(
        (option) => option.textContent,
      ),
    ).toEqual(['全部检查项', '规则 2', '规则 11', '规则 15']);
  });
});


it('keeps the issue and source excerpt without printing long rule basis paragraphs in the PDF card', () => {
  const finding={...item,finding:{...item.finding,
    location:{...item.finding.location,text_excerpt:'对应论文原文'},
    basis_details:[{id:'gbt7714-2025:general',kind:'project',text:'冗长的项目规则依据全文'}],
    evidence:[{id:'norm',kind:'normative_span',quote:'冗长的规范条款全文'},{id:'source',kind:'source_span',quote:'引用证据原文'}],
  }};
  render(<FindingsPane findings={[finding as PaperLintFindingItem]} rules={[]} activeFindingKey={item.key} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
  expect(screen.getByText(item.finding.message)).toBeInTheDocument();
  expect(screen.getByText('引用证据原文')).toBeInTheDocument();
  expect(screen.getByText('原文：对应论文原文')).toBeInTheDocument();
  expect(screen.queryByText('冗长的项目规则依据全文')).not.toBeInTheDocument();
  expect(screen.queryByText('冗长的规范条款全文')).not.toBeInTheDocument();
});
