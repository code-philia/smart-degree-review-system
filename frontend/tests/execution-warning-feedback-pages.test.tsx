import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import PaperLintReportPage from '../src/pages/PaperLintReportPage';
import NormativeCheckPage from '../src/pages/NormativeCheckPage';
import { deleteFindingFeedback, fetchFindingFeedback, saveFindingFeedback } from '../src/api/feedback';
import { fixture } from './fixtures/reportExport';
import { fetchPaperLintJob, fetchPaperLintReport, runReviewPilotPaperLint, type PaperLintRunResponse } from '../src/api/paperLint';

const numericRule = 'abstract_numeric_consistency_check';
const warningId = `execution-warning:${numericRule}:precondition:abstract_numeric`;
const numericReport: PaperLintRunResponse = { ...fixture, id: 'warning-report', selected_rule_ids: [numericRule], result: { ...fixture.result, rule_runs: [{ rule_id: numericRule, rule_run_id: 'numeric', severity: 'warning', execution_status: 'completed', outcome: 'not_applicable', findings: [], params: { preconditions: [{ id: 'abstract_numeric', passed: false, status: 'failed' }] } }] } };

vi.mock('../src/auth/AuthSessionProvider', () => ({ useAuthSession: () => ({ status: 'authenticated', user: { id: 'test' } }) }));
vi.mock('../src/hooks/usePaperLintRepairSuggestions', () => ({ usePaperLintRepairSuggestions: () => ({ repairSuggestionByFindingKey: {}, supportsRepairSuggestion: () => false }) }));
vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => null }));
vi.mock('../src/api/paperLint', async () => ({
  ...(await vi.importActual('../src/api/paperLint')),
  fetchPaperLintReport: vi.fn(async () => numericReport),
  runReviewPilotPaperLint: vi.fn(),
  fetchPaperLintJob: vi.fn(async () => ({ status: 'completed', report_id: 'warning-report' })),
  fetchPaperLintDocumentMetrics: vi.fn(async () => ({ page_count: 20, word_count: 12345, text_available: true })),
  fetchReviewPilotPaperLintRules: vi.fn(async () => ({ rules: [{ rule_id: 'abstract_numeric_consistency_check', title: '论点论据一致性检测', available: true, default_enabled: true, enabled_in_mvp: true }] })),
}));
vi.mock('../src/api/feedback', async () => ({
  ...(await vi.importActual('../src/api/feedback')),
  fetchFindingFeedback: vi.fn(async (_reportId: string, _ruleId: string, findingId: string) => {
    if (findingId === 'unsupported-finding') throw Object.assign(new Error('该规则暂不支持 AI 修复建议'), { status: 422 });
    return { id: 'warning-feedback', feedback_value: 'negative', reason_code: 'false_positive', reason_text: '摘要中已有数值', created_at: '', updated_at: '' };
  }),
  saveFindingFeedback: vi.fn(),
  deleteFindingFeedback: vi.fn(async () => {}),
}));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

it.each([['history', false], ['completed', false], ['history', true], ['completed', true]] as const)('restores and edits warning feedback on %s report (another finding GET rejects: %s)', async (page, mixed) => {
  if (mixed) vi.mocked(fetchPaperLintReport).mockResolvedValueOnce({
    ...numericReport, selected_rule_ids: [numericRule, 'saved_custom_rule'],
    result: { ...numericReport.result, rule_runs: [...numericReport.result.rule_runs, {
      rule_id: 'saved_custom_rule', rule_run_id: 'unsupported-feedback', severity: 'warning', execution_status: 'completed', outcome: 'issues_found',
      findings: [{ finding_id: 'unsupported-finding', rule_id: 'saved_custom_rule', message: '实际问题' }],
    }] },
  });
  localStorage.setItem('numeric-review-active-job:test', JSON.stringify({ jobId: 'job', requestId: 'request', filename: 'test.pdf', selectedRuleIds: [numericRule] }));
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/reports/warning-report']}><Routes><Route path="/reports/:reportId" element={page === 'history' ? <PaperLintReportPage /> : <NormativeCheckPage mode="semantic" />} /></Routes></MemoryRouter>);
  await waitFor(() => expect(fetchFindingFeedback).toHaveBeenCalledWith('warning-report', numericRule, warningId));
  const article = (await screen.findByRole('heading', { name: '摘要中不存在可核验的含有数值的论点' })).closest('article')!;
  const controls = within(article);
  await waitFor(() => expect(controls.getByRole('button', { name: '需要改进' })).toHaveAttribute('aria-pressed', 'true'));
  expect(controls.getByRole('combobox', { name: '负面反馈原因' })).toHaveValue('false_positive');
  expect(controls.getByRole('textbox', { name: '反馈补充说明' })).toHaveValue('摘要中已有数值');
  if (mixed) {
    expect(fetchFindingFeedback).toHaveBeenCalledWith('warning-report', 'saved_custom_rule', 'unsupported-finding');
    const unsupported = within(screen.getByText('实际问题').closest('article')!);
    expect(unsupported.getByRole('button', { name: '需要改进' })).toHaveAttribute('aria-pressed', 'false');
    expect(unsupported.queryByRole('textbox', { name: '反馈补充说明' })).not.toBeInTheDocument();
  }

  vi.mocked(saveFindingFeedback).mockRejectedValueOnce(new Error('保存服务暂不可用'));
  await user.click(controls.getByRole('button', { name: '提交反馈' }));
  expect(await controls.findByRole('alert')).toHaveTextContent('保存服务暂不可用');
  expect(screen.queryByRole('heading', { name: '提交成功' })).not.toBeInTheDocument();
  vi.mocked(saveFindingFeedback).mockResolvedValueOnce({ id: 'warning-feedback', feedback_value: 'negative', reason_code: 'description_unclear', reason_text: '请进一步说明', created_at: '', updated_at: '' });
  await user.selectOptions(controls.getByRole('combobox', { name: '负面反馈原因' }), 'description_unclear');
  await user.clear(controls.getByRole('textbox', { name: '反馈补充说明' }));
  await user.type(controls.getByRole('textbox', { name: '反馈补充说明' }), '请进一步说明');
  await user.click(controls.getByRole('button', { name: '提交反馈' }));
  expect(await screen.findByRole('heading', { name: '提交成功' })).toBeInTheDocument();
  expect(saveFindingFeedback).toHaveBeenLastCalledWith('warning-report', numericRule, warningId, { feedback_value: 'negative', reason_code: 'description_unclear', reason_text: '请进一步说明' });
  await user.click(screen.getByRole('button', { name: '知道了' }));
  await user.click(controls.getByRole('button', { name: '取消评价' }));
  await waitFor(() => expect(deleteFindingFeedback).toHaveBeenCalledWith('warning-report', numericRule, warningId));
  expect(controls.queryByRole('textbox', { name: '反馈补充说明' })).not.toBeInTheDocument();
});


function NextHistoryReport() {
  const navigate = useNavigate();
  return <><button onClick={() => navigate('/reports/report-b')}>查看下一份报告</button><PaperLintReportPage /></>;
}

it.each(['history', 'completed'] as const)('does not show another report rating while the %s report feedback is loading or rejected', async page => {
  const reportA = { ...numericReport, id: 'report-a' };
  const reportB = { ...numericReport, id: 'report-b' };
  vi.mocked(fetchPaperLintReport).mockResolvedValueOnce(reportA);
  if (page === 'history') vi.mocked(fetchPaperLintReport).mockResolvedValueOnce(reportB);
  else vi.mocked(runReviewPilotPaperLint).mockResolvedValueOnce(reportB);
  let rejectNext!: (error: Error) => void;
  vi.mocked(fetchFindingFeedback).mockImplementationOnce(async () => ({ id: 'feedback-a', feedback_value: 'negative', reason_code: 'false_positive', reason_text: '仅属于报告 A', created_at: '', updated_at: '' }))
    .mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectNext = reject; }));
  if (page === 'completed') localStorage.setItem('numeric-review-active-job:test', JSON.stringify({ jobId: 'job-a', requestId: 'request-a', filename: 'a.pdf', selectedRuleIds: [numericRule] }));
  const user = userEvent.setup();
  render(<MemoryRouter initialEntries={['/reports/report-a']}><Routes><Route path="/reports/:reportId" element={page === 'history' ? <NextHistoryReport /> : <NormativeCheckPage mode="semantic" />} /></Routes></MemoryRouter>);
  await screen.findByDisplayValue('仅属于报告 A');
  if (page === 'history') await user.click(screen.getByRole('button', { name: '查看下一份报告' }));
  else {
    await user.upload(screen.getByLabelText('上传待审查 PDF'), new File(['%PDF-1.7'], 'b.pdf', { type: 'application/pdf' }));
    await user.click(screen.getByRole('button', { name: '开始检查' }));
  }
  await waitFor(() => expect(fetchFindingFeedback).toHaveBeenCalledWith('report-b', numericRule, warningId));
  const controls = within((await screen.findByRole('heading', { name: '摘要中不存在可核验的含有数值的论点' })).closest('article')!);
  expect(controls.getByRole('button', { name: '需要改进' })).toHaveAttribute('aria-pressed', 'false');
  expect(controls.queryByRole('textbox', { name: '反馈补充说明' })).not.toBeInTheDocument();
  await act(async () => rejectNext(new Error('反馈加载暂不可用')));
  expect(controls.getByRole('button', { name: '需要改进' })).toHaveAttribute('aria-pressed', 'false');
  expect(controls.queryByRole('textbox', { name: '反馈补充说明' })).not.toBeInTheDocument();
});

it.each(['failed', 'completed'] as const)('does not enable report feedback when a %s job retains partial results without a saved report', async status => {
  const user = userEvent.setup();
  vi.mocked(runReviewPilotPaperLint).mockResolvedValueOnce({ job_id: 'unsaved-job', status: 'running', report_id: null, error_message: null, created_at: '', updated_at: '' });
  vi.mocked(fetchPaperLintJob).mockResolvedValueOnce({ job_id: 'unsaved-job', status, report_id: null, error_message: status === 'failed' ? '检测服务中断' : null, created_at: '', updated_at: '', progress: { completed_rule_ids: [numericRule], total_rule_ids: [numericRule], rule_runs: numericReport.result.rule_runs } });
  render(<MemoryRouter><NormativeCheckPage mode="semantic" /></MemoryRouter>);
  await screen.findByText('论点论据一致性检测');
  await user.upload(screen.getByLabelText('上传待审查 PDF'), new File(['%PDF-1.7'], 'partial.pdf', { type: 'application/pdf' }));
  await user.click(screen.getByRole('button', { name: '开始检查' }));
  expect(await screen.findByText(status === 'failed' ? '检测服务中断' : '检测完成，但报告未保存，请重试')).toBeInTheDocument();
  expect(await screen.findByRole('heading', { name: '摘要中不存在可核验的含有数值的论点' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '有帮助' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '需要改进' })).not.toBeInTheDocument();
  expect(fetchFindingFeedback).not.toHaveBeenCalled();
});
