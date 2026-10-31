import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import NormativeCheckPage from '../src/pages/NormativeCheckPage';
import { cancelPaperLintJob, fetchPaperLintJob, fetchPaperLintReport, fetchReviewPilotPaperLintRules, runReviewPilotPaperLint } from '../src/api/paperLint';
const { user } = vi.hoisted(() => ({ user: { id: 'student01' } }));
vi.mock('../src/auth/AuthSessionProvider', () => ({ useAuthSession: () => ({ status: 'authenticated', user }) }));
vi.mock('../src/api/paperLint', async () => ({
  ...await vi.importActual('../src/api/paperLint'),
  cancelPaperLintJob: vi.fn(), fetchPaperLintJob: vi.fn(), fetchPaperLintReport: vi.fn(),
  fetchReviewPilotPaperLintRules: vi.fn(), runReviewPilotPaperLint: vi.fn(),
}));
vi.mock('../src/components/paperLint/Workspace', () => ({ PaperLintWorkspace: () => <div /> }));
const job = { job_id: 'active-check', status: 'running' as const, report_id: null, error_message: null, created_at: '', updated_at: '' };

beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks();
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({
    engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: '',
    rules: [{ rule_id: 'sjtu_rule_22', title: '正文引文引用编号缺失', description: '', default_severity: 'warning',
      default_enabled: true, enabled_in_mvp: true, available: true, uses_external_model: false, execution_mode: 'deterministic' }],
  });
  vi.mocked(runReviewPilotPaperLint).mockResolvedValue(job);
  vi.mocked(cancelPaperLintJob).mockResolvedValue({ ...job, status: 'cancelled' });
});

it('stops the backend check, clears recovery state and ignores a late completed poll', async () => {
  let finishPoll!: (value: typeof job) => void;
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(resolve => { finishPoll = resolve; }));
  render(<MemoryRouter><NormativeCheckPage mode="thirty" /></MemoryRouter>);
  await screen.findByText('已选择全部检测规则');
  fireEvent.change(screen.getByLabelText('上传待审查 PDF'), { target: { files: [new File(['%PDF-1.7'], 'check.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: '开始检测' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '停止检测' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '停止检测' }));
  expect(await screen.findByText('已停止检测，可以重新开始。')).toBeInTheDocument();
  expect(cancelPaperLintJob).toHaveBeenCalledWith('active-check');
  expect(localStorage.getItem('paper-lint-active-job:student01')).toBeNull();
  await act(async () => { finishPoll({ ...job, status: 'completed', report_id: 'late-report' } as never); });
  expect(fetchPaperLintReport).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: '开始检测' })).toBeEnabled();
});

it('can stop a restored background check without reuploading its PDF', async () => {
  localStorage.setItem('paper-lint-active-job:student01', JSON.stringify({ jobId: job.job_id, requestId: 'request-1', filename: 'previous.pdf', selectedRuleIds: ['sjtu_rule_22'] }));
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(() => {}));
  render(<MemoryRouter><NormativeCheckPage mode="thirty" /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: '停止检测' }));
  expect(await screen.findByText('已停止检测，可以重新开始。')).toBeInTheDocument();
  expect(cancelPaperLintJob).toHaveBeenCalledWith(job.job_id);
  expect(runReviewPilotPaperLint).not.toHaveBeenCalled();
});

it('keeps Start disabled until cancellation cleanup finishes even when polling already sees cancelled', async () => {
  let finishPoll!: (value: any) => void;
  let finishCancel!: (value: any) => void;
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(resolve => { finishPoll = resolve; }));
  vi.mocked(cancelPaperLintJob).mockImplementationOnce(() => new Promise(resolve => { finishCancel = resolve; }));
  render(<MemoryRouter><NormativeCheckPage mode="thirty" /></MemoryRouter>);
  await screen.findByText('已选择全部检测规则');
  fireEvent.change(screen.getByLabelText('上传待审查 PDF'), { target: { files: [new File(['%PDF-1.7'], 'check.pdf', { type: 'application/pdf' })] } });
  fireEvent.click(screen.getByRole('button', { name: '开始检测' }));
  await waitFor(() => expect(screen.getByRole('button', { name: '停止检测' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: '停止检测' }));
  await act(async () => { finishPoll({ ...job, status: 'cancelled' }); });
  expect(screen.getByRole('button', { name: '检测进行中' })).toBeDisabled();
  await act(async () => { finishCancel({ ...job, status: 'cancelled' }); });
  expect(screen.getByRole('button', { name: '开始检测' })).toBeEnabled();
});
