import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import type { PaperLintFindingItem, RuleExecutionWarning } from '../src/components/paperLint/model';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';

const numeric = 'abstract_numeric_consistency_check';
const rules = [
  { rule_id: 'sjtu_rule_31', title: '规则31' }, { rule_id: 'sjtu_rule_2', title: '规则2' },
  { rule_id: 'typo_detection_check', title: '错别字' }, { rule_id: numeric, title: '数值一致性' },
];
function finding(key: string, ruleId: string, severity: 'error' | 'warning' | 'info', page: number, index: number): PaperLintFindingItem {
  return { key, index, ruleRun: { rule_id: ruleId, rule_run_id: ruleId, execution_status: 'completed', outcome: 'issues_found', severity, findings: [] },
    finding: { finding_id: key, rule_id: ruleId, message: key, location: { type: 'pdf_page', page_number: page } } };
}
const findings = [
  finding('info-2', 'sjtu_rule_2', 'info', 1, 0),
  finding('warning-numeric', numeric, 'warning', 6, 1),
  finding('error-31', 'sjtu_rule_31', 'error', 3, 2),
  finding('warning-31', 'sjtu_rule_31', 'warning', 10, 3),
  finding('warning-2-later', 'sjtu_rule_2', 'warning', 20, 4),
  finding('warning-2-first', 'sjtu_rule_2', 'warning', 2, 5),
  finding('error-2', 'sjtu_rule_2', 'error', 30, 6),
  finding('warning-typo', 'typo_detection_check', 'warning', 99, 7),
  finding('info-numeric', numeric, 'info', 1, 8),
];
const warnings: RuleExecutionWarning[] = [
  { title: '未完成数值', reason: '缺少实验数据', suggestion: '核对原文' },
  { ruleId: 'typo_detection_check', title: '未完成错别字', reason: '部分内容未完成', suggestion: '稍后重试' },
  { ruleId: 'sjtu_rule_31', title: '未完成31', reason: '部分内容未完成', suggestion: '稍后重试' },
  { ruleId: 'sjtu_rule_2', title: '未完成2', reason: '部分内容未完成', suggestion: '稍后重试' },
];
const intro = '如需使用以下规则，请按建议内容调整；如无需使用，请忽略以下内容';
const expected = ['error-2', 'error-31', 'warning-2-first', 'warning-2-later', 'warning-31', 'warning-typo', 'warning-numeric',
  '未完成2', '未完成31', '未完成错别字', '未完成数值', 'info-2', 'info-numeric'];
const props = { rules, selectedRuleIds: rules.map(rule => rule.rule_id), findings, executionWarnings: warnings,
  activeFindingKey: 'error-2', activeAnchorId: null, onAnchorClick: vi.fn() };
const cardIds = (container: HTMLElement) => Array.from(container.querySelectorAll('article'))
  .map(card => card.getAttribute('data-finding-key') || card.querySelector('h3')?.textContent);

it.each([false, true])('orders All cards by severity, dropdown rule order and PDF page without changing navigation (live=%s)', async running => {
  const original = JSON.stringify(findings);
  const onFindingClick = vi.fn();
  const { container } = render(<FindingsPane {...props} running={running} onFindingClick={onFindingClick} />);
  expect(cardIds(container)).toEqual(expected);
  expect(screen.queryByText(intro)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '跳到 PDF 第 30 页' }));
  expect(onFindingClick).toHaveBeenCalledWith('error-2');
  expect(container.querySelector('[data-finding-key="error-2"]')).toHaveAttribute('aria-current', 'true');
  expect(JSON.stringify(findings)).toBe(original);
  fireEvent.keyDown(screen.getByRole('combobox'), { key: 'ArrowDown' });
  const list = await screen.findByRole('listbox');
  const rule = within(list).getByRole('option', { name: /^规则2，/ });
  act(() => { rule.focus(); fireEvent.keyDown(rule, { key: 'Enter' }); });
  expect(cardIds(container)).toEqual(['error-2', 'warning-2-first', 'warning-2-later', '未完成2', 'info-2']);
});

it('keeps the instruction in the dedicated execution category and restores the ordered All list', () => {
  const { container } = render(<FindingsPane {...props} onFindingClick={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: '规则未实现警告 4', exact: true }));
  expect(screen.getByText(intro)).toBeInTheDocument();
  expect(container.querySelectorAll('article')).toHaveLength(4);
  expect(container.querySelector('[data-finding-key]')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '全部', exact: true }));
  expect(cardIds(container)).toEqual(expected);
  expect(screen.queryByText(intro)).not.toBeInTheDocument();
});
