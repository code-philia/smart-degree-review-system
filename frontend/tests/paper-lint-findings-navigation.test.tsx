import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
  it('exposes an article with a keyboard-operable title separate from its other controls', async () => {
    const user = userEvent.setup();
    const onFindingClick = vi.fn();
    render(<FindingsPane findings={[item]} rules={[]} activeFindingKey={item.key} activeAnchorId={null}
      onFindingClick={onFindingClick} onAnchorClick={vi.fn()} />);

    const card = screen.getByRole('article');
    const title = within(within(card).getByRole('heading', { level: 3 })).getByRole('button');
    expect(title).toHaveAttribute('aria-current', 'true');
    expect(card).not.toHaveAttribute('tabindex');
    for (const button of within(card).getAllByRole('button')) {
      expect(button.parentElement?.closest('button, [role="button"]')).toBeNull();
    }

    // Tabbing into a card first reaches its title, then the independent controls.
    screen.getByRole('combobox', { name: '按检查项筛选' }).focus();
    await user.tab();
    expect(title).toHaveFocus();
    await user.keyboard('{Enter} ');
    expect(onFindingClick.mock.calls).toEqual([[item.key], [item.key]]);
    await user.tab();
    expect(within(card).getByRole('button', { name: '标记为已处理' })).toHaveFocus();
  });

  it('selects from the card body and title without duplicating the page-jump action', async () => {
    const user = userEvent.setup();
    const onFindingClick = vi.fn();
    render(<FindingsPane findings={[item]} rules={[]} activeFindingKey={null} activeAnchorId={null}
      onFindingClick={onFindingClick} onAnchorClick={vi.fn()} />);
    const card = screen.getByRole('article');
    await user.click(card);
    await user.click(within(card).getByText(item.finding.message));
    await user.click(within(within(card).getByRole('heading', { level: 3 })).getByRole('button'));
    const jump = within(card).getByRole('button', { name: '跳到 PDF 第 99 页' });
    await user.click(jump);
    await user.keyboard('{Enter} ');
    expect(onFindingClick.mock.calls).toEqual(Array.from({ length: 6 }, () => [item.key]));
  });

  it('keeps handled, repair, feedback and evidence controls independent of card selection', async () => {
    const user = userEvent.setup();
    const onFindingClick = vi.fn();
    const onAnchorClick = vi.fn();
    const onGenerateRepairSuggestion = vi.fn();
    const onFindingFeedback = vi.fn();
    const anchoredItem = { ...item, finding: { ...item.finding, anchors: [
      { anchor_id: 'source-99', role: 'source_span', label: '证据 1', location: item.finding.location! },
    ] } };
    render(<FindingsPane findings={[anchoredItem]} rules={[]} activeFindingKey={item.key} activeAnchorId={null}
      onFindingClick={onFindingClick} onAnchorClick={onAnchorClick}
      onGenerateRepairSuggestion={onGenerateRepairSuggestion} onFindingFeedback={onFindingFeedback} />);
    const card = screen.getByRole('article');
    const handled = within(card).getByRole('button', { name: '标记为已处理' });
    handled.focus();
    await user.keyboard('{Enter}');
    expect(within(card).getByText('已标记为本次已处理')).toBeInTheDocument();
    await user.keyboard(' ');
    expect(within(card).queryByText('已标记为本次已处理')).toBeNull();

    const repair = within(card).getByRole('button', { name: '获取修复建议' });
    await user.click(repair);
    await user.keyboard('{Enter} ');
    expect(onGenerateRepairSuggestion.mock.calls).toEqual([[anchoredItem], [anchoredItem], [anchoredItem]]);
    await user.click(within(card).getByRole('button', { name: '有帮助' }));
    expect(onFindingFeedback).toHaveBeenCalledExactlyOnceWith(anchoredItem, 'positive');
    const evidence = within(card).getByRole('button', { name: '证据 1' });
    await user.click(evidence);
    await user.keyboard('{Enter} ');
    expect(onAnchorClick.mock.calls).toEqual([[item.key, 'source-99'], [item.key, 'source-99'], [item.key, 'source-99']]);
    expect(onFindingClick).not.toHaveBeenCalled();
  });

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
  it('lists numbered checks numerically despite out-of-order input', async () => {
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
    fireEvent.keyDown(screen.getByRole('combobox', { name: '按检查项筛选' }), { key: 'ArrowDown' });
    const list = await screen.findByRole('listbox');
    expect(within(list).getAllByRole('option').map(option => option.textContent?.split('，')[0])).toEqual([
      '全部检查项', '规则 2', '规则 11', '规则 15',
    ]);
  });
});


it('keeps the issue and PDF navigation without printing evidence or long rule basis paragraphs in the PDF card', () => {
  const finding={...item,finding:{...item.finding,
    location:{...item.finding.location,text_excerpt:'对应论文原文'},
    basis_details:[{id:'gbt7714-2025:general',kind:'project',text:'冗长的项目规则依据全文'}],
    evidence:[{id:'norm',kind:'normative_span',quote:'冗长的规范条款全文'},{id:'source',kind:'source_span',quote:'引用证据原文'}],
  }};
  render(<FindingsPane findings={[finding as PaperLintFindingItem]} rules={[]} activeFindingKey={item.key} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
  expect(screen.getByText(item.finding.message)).toBeInTheDocument();
  expect(screen.queryByText('引用证据原文')).not.toBeInTheDocument();
  expect(screen.queryByText('原文：对应论文原文')).not.toBeInTheDocument();
  expect(screen.queryByText('冗长的项目规则依据全文')).not.toBeInTheDocument();
  expect(screen.queryByText('冗长的规范条款全文')).not.toBeInTheDocument();
});

describe('repair suggestion card', () => {
  it('renders a generated suggestion and lets the parent request one', () => {
    const onGenerateRepairSuggestion = vi.fn();
    const onLoadRepairSuggestion = vi.fn();
    render(
      <FindingsPane
        findings={[item]}
        rules={[]}
        activeFindingKey="finding-99"
        activeAnchorId={null}
        onFindingClick={vi.fn()}
        onAnchorClick={vi.fn()}
        onLoadRepairSuggestion={onLoadRepairSuggestion}
        onGenerateRepairSuggestion={onGenerateRepairSuggestion}
        repairSuggestionByFindingKey={{
          'finding-99': {
            schema_version: 'repair-response-v2',
            rule_id: 'sjtu_rule_24',
            finding_id: 'finding-99',
            status: 'suggested',
            actions: [{ instruction: '检查文末条目。', evidence_ids: ['e1'] }],
            provenance: {
              provider: 'huawei_maas',
              model: 'test-model',
              model_version: 'v1',
              prompt_version: 'test-v1',
              context_sha256: 'x',
              generated_at: '2026-10-19T00:00:00.000Z',
            },
            usage: { input_tokens: 1, output_tokens: 1, attempts: 1 },
          },
        }}
      />,
    );
    expect(screen.getByText('检查文末条目。')).toBeInTheDocument();
    expect(screen.queryByText('请对照 PDF 原文核查此处，并按论文规范修订。')).not.toBeInTheDocument();
    expect(onLoadRepairSuggestion).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '重新生成修复建议' }));
    expect(onGenerateRepairSuggestion).toHaveBeenCalledWith(item);
  });

  it('shows an archived suggestion without exposing a regeneration button', () => {
    render(
      <FindingsPane
        findings={[item]}
        rules={[]}
        activeFindingKey="finding-99"
        activeAnchorId={null}
        onFindingClick={vi.fn()}
        onAnchorClick={vi.fn()}
        onLoadRepairSuggestion={vi.fn()}
        repairSuggestionByFindingKey={{
          'finding-99': {
            schema_version: 'repair-response-v2',
            rule_id: 'sjtu_rule_24',
            finding_id: 'finding-99',
            status: 'suggested',
            actions: [{ instruction: '核对归档建议。', evidence_ids: ['e1'] }],
            provenance: {
              provider: 'huawei_maas', model: 'test-model', model_version: 'v1',
              prompt_version: 'test-v1', context_sha256: 'x', generated_at: '2026-10-20T00:00:00.000Z',
            },
            usage: { input_tokens: 1, output_tokens: 1, attempts: 1 },
          },
        }}
      />,
    );
    expect(screen.getByText('核对归档建议。')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /生成.*建议|重新获取建议|强制生成新版本/ })).toBeNull();
  });

  it('limits single-report suggestions to supported rules and explains evidence conflicts', () => {
    const { rerender } = render(
      <FindingsPane
        findings={[item]}
        rules={[]}
        activeFindingKey="finding-99"
        activeAnchorId={null}
        onFindingClick={vi.fn()}
        onAnchorClick={vi.fn()}
        onLoadRepairSuggestion={vi.fn()}
        onGenerateRepairSuggestion={vi.fn()}
        supportsRepairSuggestion={() => false}
      />,
    );
    expect(screen.queryByText('AI 修复建议')).toBeNull();

    rerender(
      <FindingsPane
        findings={[item]}
        rules={[]}
        activeFindingKey="finding-99"
        activeAnchorId={null}
        onFindingClick={vi.fn()}
        onAnchorClick={vi.fn()}
        onLoadRepairSuggestion={vi.fn()}
        onGenerateRepairSuggestion={vi.fn()}
        forceNewRepairSuggestion
        repairSuggestionByFindingKey={{
          'finding-99': {
            schema_version: 'repair-response-v2', rule_id: 'sjtu_rule_24', finding_id: 'finding-99',
            status: 'evidence_conflict', actions: [{ instruction: '人工复核该条告警。', evidence_ids: ['e1'] }],
            provenance: {
              provider: 'huawei_maas', model: 'test-model', model_version: 'v1',
              prompt_version: 'test-v1', context_sha256: 'x', generated_at: '2026-10-20T00:00:00.000Z',
            },
            usage: { input_tokens: 1, output_tokens: 1, attempts: 1 },
          },
        }}
      />,
    );
    expect(screen.getByRole('button', { name: '重新生成修复建议' })).toBeInTheDocument();
    expect(screen.getByText(/暂不应仅依据该告警修改论文/)).toBeInTheDocument();
  });
});


it.each([true, false])('lists every selected rule without alarms and excludes unselected catalog rules (hasFinding=%s)', async (hasFinding) => {
  const rules = [
    { rule_id: 'sjtu_rule_24', title: '参考文献引用' },
    { rule_id: 'typo_detection_check', title: '正文错别字检测' },
    { rule_id: 'abstract_numeric_consistency_check', title: '论点论据一致性检测' },
    { rule_id: 'not_selected', title: '未选择的规则' },
  ];
  render(<FindingsPane findings={hasFinding ? [item] : []} rules={rules as never} selectedRuleIds={rules.slice(0,3).map(rule => rule.rule_id)}
    activeFindingKey={null} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
  const select = screen.getByRole('combobox', { name: '按检查项筛选' });
  fireEvent.keyDown(select, { key: 'ArrowDown' });
  const list = await screen.findByRole('listbox');
  expect(within(list).getAllByRole('option').map(option => option.textContent?.split('，')[0])).toEqual(
    expect.arrayContaining(['全部检查项', '参考文献引用', '正文错别字检测', '论点论据一致性检测']),
  );
  expect(within(list).queryByText('未选择的规则')).not.toBeInTheDocument();
  const option = within(list).getByRole('option', { name: /^正文错别字检测，/ });
  option.focus(); fireEvent.keyDown(option, { key: 'Enter' });
  expect(screen.getByText('本规则未检测出问题')).toBeInTheDocument();
  expect(screen.queryByText(item.finding.message)).not.toBeInTheDocument();
});
