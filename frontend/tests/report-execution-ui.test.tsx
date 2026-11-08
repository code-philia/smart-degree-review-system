import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import type { PaperLintFindingItem, RuleExecutionWarning } from '../src/components/paperLint/model';

const run = { rule_id: 'test_rule', rule_run_id: 'run', severity: 'warning' as const,
  execution_status: 'completed' as const, outcome: 'issues_found' as const, findings: [] };
const findings: PaperLintFindingItem[] = [0, 1, 2].map(index => ({ key: `finding-${index}`, index, ruleRun: run,
  finding: { finding_id: String(index), rule_id: run.rule_id, message: `普通告警${index}` } }));
const base = { rules: [{ rule_id: run.rule_id, title: '检查规则' }], selectedRuleIds: [run.rule_id],
  ruleRuns: [run], findings, activeFindingKey: null, activeAnchorId: null,
  onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
it.each([false, true])('shows a green zero summary and the shared empty layout for execution with findings in other tiers (live=%s)', running => {
  const { container } = render(<FindingsPane {...base} running={running} />);
  fireEvent.click(screen.getByRole('button', { name: '规则未实现警告 0', exact: true }));
  expect(within(screen.getByRole('combobox')).getByText('0', { exact: true })).toBeInTheDocument();
  expect(screen.getByText('当前筛选未发现规则未实现警告')).toBeInTheDocument();
  expect(screen.getByText('当前报告共发现 3 处问题，分布在其他级别。')).toBeInTheDocument();
  expect(container.querySelectorAll('article')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: '查看全部级别' }));
  expect(container.querySelectorAll('article')).toHaveLength(3);
});

const target: PaperLintFindingItem = { key: 'warning-feedback-target', index: 0, ruleRun: run,
  finding: { finding_id: 'execution-warning:generic', rule_id: run.rule_id, message: '核验未完成' } };
const warning = { ruleId: run.rule_id, title: '规则未完成检测', reason: '核验未完成', suggestion: '稍后重试',
  feedbackTarget: target } as RuleExecutionWarning;
it.each(['all', 'execution'])('keeps warning feedback usable under %s without selecting a PDF finding', async level => {
  const onValue = vi.fn(), onReason = vi.fn(), onCancel = vi.fn(), onFindingClick = vi.fn();
  render(<FindingsPane {...base} findings={[]} executionWarnings={[warning]} onFindingClick={onFindingClick}
    findingFeedbackByKey={{ [target.key]: { id: 'saved', feedback_value: 'negative', reason_code: null,
      reason_text: null, created_at: '', updated_at: '' } }}
    onFindingFeedback={onValue} onFindingFeedbackReason={onReason} onFindingFeedbackCancel={onCancel} />);
  if (level === 'execution') fireEvent.click(screen.getByRole('button', { name: '规则未实现警告 1', exact: true }));
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: '有帮助' }));
  expect(onValue).toHaveBeenCalledWith(target, 'positive');
  await user.selectOptions(screen.getByRole('combobox', { name: '负面反馈原因' }), 'description_unclear');
  await user.type(screen.getByRole('textbox', { name: '反馈补充说明' }), '需要更明确的原因');
  await user.click(screen.getByRole('button', { name: '提交反馈' }));
  expect(onReason).toHaveBeenCalledWith(target, 'description_unclear', '需要更明确的原因');
  expect(await screen.findByRole('heading', { name: '提交成功' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: '知道了' }));
  await user.click(screen.getByRole('button', { name: '取消评价' }));
  expect(onCancel).toHaveBeenCalledWith(target);
  expect(onFindingClick).not.toHaveBeenCalled();
});
