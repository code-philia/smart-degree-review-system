import { fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import type { PaperLintRule, PaperLintRuleRun } from '../src/api/paperLint';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { LivePaperLintReport } from '../src/components/paperLint/LivePaperLintReport';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';
vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => <div /> }));
const { documentRejectionResult } = createRequire(import.meta.url)('../../backend/src/normative/paperDocumentAdmission.js');
const rules = [{ rule_id: 'required_section_completeness_check', title: '核心章节完整性' },
  { rule_id: 'abstract_numeric_consistency_check', title: '论点论据一致性检测' }] as PaperLintRule[];
const blocked: PaperLintRuleRun = { rule_run_id: 'document_admission', rule_id: 'document_type_check', severity: 'error',
  execution_status: 'completed', outcome: 'issues_found', findings: [{ finding_id: 'document_not_paper',
    rule_id: 'document_type_check', message: '上传的 PDF 不是论文，不能被 Paper Model 解析编译。所有论文规则均未检测。' }] };

it.each(['缺少中文摘要。', '缺少英文摘要（Abstract）。', '中文摘要不完整：未识别到本摘要的关键词收尾。',
  '英文摘要（Abstract）不完整：未识别到本摘要的关键词收尾。'])('renders the backend rejection cause in both report modes: %s', reason => {
  const result = documentRejectionResult({ status: 'rejected', reason_code: 'paper_structure_incomplete',
    profile: 'chinese-thesis', missing_sections: [], incomplete_sections: [], reason }, rules.map(rule => rule.rule_id));
  for (const running of [false, true]) {
    const view = render(<FindingsPane rules={rules} selectedRuleIds={rules.map(rule => rule.rule_id)} ruleRuns={result.rule_runs}
      findings={flattenPaperLintFindings(result)} running={running}
      activeFindingKey={null} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    expect(screen.getByText(result.rule_runs[0].findings[0].message)).toHaveTextContent(reason);
    expect(screen.getByRole('button', { name: '严重 1', exact: true })).toBeInTheDocument();
    expect(screen.queryByText('未检测出问题')).not.toBeInTheDocument();
    expect(screen.queryByText(/正在检测/)).not.toBeInTheDocument();
    view.unmount();
  }
});

it.each([
  [false, '摘要缺失，Paper Model 编译失败。所有论文规则均未检测。'],
  [true, '摘要缺失，Paper Model 编译失败。所有论文规则均未检测。'],
  [false, '英文摘要不完整：未识别到本摘要的关键词收尾。所有论文规则均未检测。'],
  [true, '英文摘要不完整：未识别到本摘要的关键词收尾。所有论文规则均未检测。'],
])('preserves the precise structural failure in formal/live results (%s)', (running, message) => {
  const run = { ...blocked, findings: [{ ...blocked.findings[0], message }] };
  render(<FindingsPane rules={rules} selectedRuleIds={rules.map(rule => rule.rule_id)} ruleRuns={[run]}
    findings={flattenPaperLintFindings({ rule_runs: [run] })} running={running as boolean}
    activeFindingKey={null} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
  expect(screen.getByText(message as string)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '严重 1', exact: true })).toBeInTheDocument();
  expect(screen.queryByText('未检测出问题')).not.toBeInTheDocument();
});

it.each([false, true])('shows only the severe document failure with no passing or running thesis rules (live=%s)', async running => {
  render(<FindingsPane rules={rules} selectedRuleIds={rules.map(rule => rule.rule_id)} ruleRuns={[blocked]}
    findings={flattenPaperLintFindings({ rule_runs: [blocked] })} running={running}
    activeFindingKey={null} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '严重 1', exact: true }));
  expect(screen.getByText(/上传的 PDF 不是论文/)).toBeInTheDocument();
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const menu = await screen.findByRole('listbox');
  expect(within(menu).getByRole('option', { name: '论文编译校验，问题总数 1 处，严重 1 处' })).toBeInTheDocument();
  expect(within(menu).queryByText('核心章节完整性')).not.toBeInTheDocument();
  expect(within(menu).queryByText('论点论据一致性检测')).not.toBeInTheDocument();
  expect(screen.queryByText(/正在检测/)).not.toBeInTheDocument();
});

it('stops live loading after document rejection while retaining zero warning statistics', () => {
  render(<LivePaperLintReport file={{ name: 'form.pdf', url: '/form.pdf' }} rules={rules} runs={[blocked]}
    selectedRuleIds={rules.map(rule => rule.rule_id)} />);
  expect(screen.getByText('规则未实现警告数').closest('div')).toHaveTextContent('0');
  expect(screen.getByRole('status')).toHaveTextContent('所有论文规则均未检测');
  expect(screen.queryByText(/检测进行中/)).not.toBeInTheDocument();
});

it('clears a pending selected rule when rejection arrives instead of hiding the severe finding', async () => {
  const props = { rules, selectedRuleIds: rules.map(rule => rule.rule_id), running: true,
    activeFindingKey: null, activeAnchorId: null, onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
  const { rerender } = render(<FindingsPane {...props} ruleRuns={[]} findings={[]} />);
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const option = await screen.findByRole('option', { name: '核心章节完整性，正在检测' });
  option.focus(); fireEvent.keyDown(option, { key: 'Enter' });
  rerender(<FindingsPane {...props} ruleRuns={[blocked]} findings={flattenPaperLintFindings({ rule_runs: [blocked] })} />);
  expect(screen.getByText(/上传的 PDF 不是论文/)).toBeInTheDocument();
  expect(screen.queryByText('未检测出问题')).not.toBeInTheDocument();
});
