import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { PaperLintFindingAnchor, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
import { clearTranslations, setLocale } from '../src/i18n/locale';

const rule = 'abstract_numeric_consistency_check';
function anchor(id: string, page: number, quote: string): PaperLintFindingAnchor {
  return { anchor_id: id, role: 'source_span', location: { type: 'pdf_page', page_number: page, text_excerpt: quote } };
}
function example(): PaperLintRuleRun {
  return { rule_id: rule, rule_run_id: 'source-region-run', severity: 'warning', execution_status: 'completed', outcome: 'issues_found', findings: [], params: {
    numeric_results: [{ declaration_id: 'd1', status: 'inconsistent',
      declaration: { id: 'd1', text: 'F1得分达到0.80。', metric: 'F1得分', number: '0.80' },
      reason: '声明称F1得分达到0.80。' + '当前检测核验已保存的实验条件，保留不同数据集和实验设置的适用范围。'.repeat(5)
        + '实验结果证据1显示数据集甲下F1为0.72。实验结果证据2显示数据集乙下F1为0.75。实验结果证据3显示数据集丙下F1为0.77。原报告认为声明数值与这些实验结果不一致。',
      suggestion: '请核对摘要中的数值与实验条件。',
      evidence: [
        { candidate_id: 'd1:t1', quote: '数据集甲下F1为0.72。' },
        { candidate_id: 'd1:t2', quote: '数据集乙下F1为0.75。' },
        { candidate_id: 'd1:t3', quote: '数据集丙下F1为0.77。' },
      ],
      abstract_anchors: [anchor('abstract-d1', 4, 'F1得分达到0.80。')],
      // Stored anchor order need not match the visible evidence order.
      evidence_anchors: [anchor('d1:t3', 53, '数据集丙下F1为0.77。'), anchor('d1:t1', 51, '数据集甲下F1为0.72。'), anchor('d1:t2', 52, '数据集乙下F1为0.75。')],
    }],
  } };
}
function show(run = example()) {
  const findings = flattenPaperLintFindings({ rule_runs: [run] });
  const onFindingClick = vi.fn(), onAnchorClick = vi.fn();
  render(<FindingsPane findings={findings} rules={[]} activeFindingKey={findings[0].key} activeAnchorId={null}
    onFindingClick={onFindingClick} onAnchorClick={onAnchorClick} />);
  return { findingKey: findings[0].key, onFindingClick, onAnchorClick };
}
beforeEach(() => { act(() => { setLocale('zh'); clearTranslations(); }); });
afterEach(() => { cleanup(); act(() => { setLocale('zh'); clearTranslations(); }); });

it('navigates from the claim content to its saved abstract anchor with exactly two callback arguments', async () => {
  const run = example(), original = JSON.stringify(run);
  const { findingKey, onAnchorClick, onFindingClick } = show(run);
  const surface = within(screen.getByRole('region', { name: '论点' })).getByRole('link', { name: '查看论点原文' });
  await userEvent.click(within(surface).getByText('F1得分达到0.80。'));
  expect(onAnchorClick.mock.calls).toEqual([[findingKey, 'abstract-d1']]);
  expect(onFindingClick).not.toHaveBeenCalled();
  expect(JSON.stringify(run)).toBe(original);
});

it('navigates each visible evidence content region to its own anchor rather than the first stored anchor', async () => {
  const { findingKey, onAnchorClick, onFindingClick } = show();
  const evidence = screen.getByRole('region', { name: '论据' });
  for (const index of [1, 2, 3]) {
    const surface = within(evidence).getByRole('link', { name: `查看论据 ${index} 原文` });
    await userEvent.click(surface);
  }
  expect(onAnchorClick.mock.calls).toEqual([[findingKey, 'd1:t1'], [findingKey, 'd1:t2'], [findingKey, 'd1:t3']]);
  expect(onFindingClick).not.toHaveBeenCalled();
});

it('lets keyboard users focus a source content region and follow it with Enter', async () => {
  const { findingKey, onAnchorClick, onFindingClick } = show();
  const surface = screen.getByRole('link', { name: '查看论据 2 原文' });
  expect(surface).toHaveAttribute('tabindex', '0');
  surface.focus();
  expect(surface).toHaveFocus();
  await userEvent.keyboard('{Enter}');
  expect(onAnchorClick.mock.calls).toEqual([[findingKey, 'd1:t2']]);
  expect(onFindingClick).not.toHaveBeenCalled();
});

it('links the discrepancy explanation to the first saved usable evidence while keeping disclosures independent', async () => {
  const { findingKey, onAnchorClick, onFindingClick } = show();
  const discrepancy = screen.getByRole('region', { name: '不一致处' });
  const surface = within(discrepancy).getByRole('link', { name: '查看相关论据原文' });
  await userEvent.click(surface);
  expect(onAnchorClick.mock.calls).toEqual([[findingKey, 'd1:t1']]);
  onAnchorClick.mockClear();
  const disclosure = within(discrepancy).getByText('查看完整分析');
  expect(surface.contains(disclosure)).toBe(false);
  await userEvent.click(disclosure);
  expect(disclosure.closest('details')).toHaveAttribute('open');
  await userEvent.click(screen.getByText('修改建议'));
  expect(screen.getByText('修改建议').closest('details')).toHaveAttribute('open');
  expect(onAnchorClick).not.toHaveBeenCalled();
  expect(onFindingClick).not.toHaveBeenCalled();
});

it('keeps explicit source buttons outside the content links and preserves one exact navigation per click', async () => {
  const { findingKey, onAnchorClick, onFindingClick } = show();
  for (const name of ['查看论点原文', '查看论据 1 原文', '查看论据 2 原文', '查看论据 3 原文']) {
    const button = screen.getByRole('button', { name });
    expect(button.closest('[role="link"]')).toBeNull();
    await userEvent.click(button);
  }
  expect(onAnchorClick.mock.calls).toEqual([[findingKey, 'abstract-d1'], [findingKey, 'd1:t1'], [findingKey, 'd1:t2'], [findingKey, 'd1:t3']]);
  expect(onFindingClick).not.toHaveBeenCalled();
});

it('does not make missing or invalid stored locations clickable or fall back to the abstract on content clicks', async () => {
  const run = example(), row = (run.params!.numeric_results as any[])[0];
  row.abstract_anchors = [];
  row.evidence_anchors = [anchor('d1:t1', 0, '数据集甲下F1为0.72。')];
  const { onAnchorClick, onFindingClick } = show(run);
  for (const name of ['论点', '论据', '不一致处']) {
    expect(within(screen.getByRole('region', { name })).queryByRole('link')).not.toBeInTheDocument();
  }
  await userEvent.click(screen.getByText('F1得分达到0.80。'));
  await userEvent.click(within(screen.getByRole('region', { name: '论据' })).getByText('数据集乙下F1为0.75。', { exact: false }));
  expect(onAnchorClick).not.toHaveBeenCalled();
  expect(onFindingClick).not.toHaveBeenCalled();
});

it('does not invent an evidence anchor from the abstract when only the claim can be located', () => {
  const run = example(), row = (run.params!.numeric_results as any[])[0];
  row.evidence_anchors = [];
  show(run);
  expect(screen.getByRole('link', { name: '查看论点原文' })).toBeVisible();
  expect(within(screen.getByRole('region', { name: '论据' })).queryByRole('link')).not.toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: '不一致处' })).queryByRole('link')).not.toBeInTheDocument();
});

it('uses the next evidence location for discrepancy navigation when the first saved evidence has no usable location', async () => {
  const run = example(), row = (run.params!.numeric_results as any[])[0];
  row.evidence_anchors = [anchor('d1:t3', 53, '数据集丙下F1为0.77。'), anchor('d1:t2', 52, '数据集乙下F1为0.75。')];
  const { findingKey, onAnchorClick, onFindingClick } = show(run);
  fireEvent.keyDown(screen.getByRole('link', { name: '查看相关论据原文' }), { key: 'Enter' });
  expect(onAnchorClick.mock.calls).toEqual([[findingKey, 'd1:t2']]);
  expect(onFindingClick).not.toHaveBeenCalled();
});
