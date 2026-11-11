import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import NormativeCheckPage from '../src/pages/NormativeCheckPage';
import { cancelPaperLintJob, fetchPaperLintJob, fetchPaperLintReport, fetchReviewPilotPaperLintRules, runReviewPilotPaperLint } from '../src/api/paperLint';
import { setLocale, translate } from '../src/i18n/locale';
import { fixture } from './fixtures/reportExport';
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
  localStorage.clear(); vi.clearAllMocks(); setLocale('zh');
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

afterEach(() => setLocale('zh'));

function restoredCheck() {
  localStorage.setItem('paper-lint-active-job:student01', JSON.stringify({ jobId: job.job_id, requestId: 'request-1', filename: 'previous.pdf', selectedRuleIds: ['sjtu_rule_22'] }));
  return render(<MemoryRouter initialEntries={['/paper-upload']}><Routes>
    <Route path="/paper-upload" element={<NormativeCheckPage mode="thirty" />} />
    <Route path="/reports/pdf/:id" element={<p>Saved report opened</p>} />
  </Routes></MemoryRouter>);
}

it.each(['zh','en'])('clearly tells the %s user a completed check cannot be cancelled before opening its report', async locale => {
  setLocale(locale);
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(() => {}));
  vi.mocked(cancelPaperLintJob).mockResolvedValue({ ...job, status: 'completed', report_id: 'finished-report' });
  vi.mocked(fetchPaperLintReport).mockResolvedValue({ ...fixture, id: 'finished-report' });
  restoredCheck();
  fireEvent.click(await screen.findByRole('button', { name: translate('停止检测') }));
  const notice = await screen.findByRole('alertdialog');
  expect(notice).toHaveTextContent(locale === 'en' ? 'The review has already finished and cannot be cancelled. You can view your report.' : '检测已完成，无法取消。您可以查看检测报告。');
  expect(screen.queryByText('已停止检测，可以重新开始。')).not.toBeInTheDocument();
  expect(fetchPaperLintReport).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: locale === 'en' ? 'View report' : '查看检测报告' }));
  expect(await screen.findByText('Saved report opened')).toBeInTheDocument();
  expect(fetchPaperLintReport).toHaveBeenCalledWith('finished-report');
});

it('does not let a completed poll bypass the cancellation outcome while the cancel request is pending', async () => {
  let finishPoll!: (value: any) => void, finishCancel!: (value: any) => void;
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(resolve => { finishPoll = resolve; }));
  vi.mocked(cancelPaperLintJob).mockImplementation(() => new Promise(resolve => { finishCancel = resolve; }));
  vi.mocked(fetchPaperLintReport).mockResolvedValue({ ...fixture, id: 'finished-report' });
  restoredCheck();
  fireEvent.click(await screen.findByRole('button', { name: '停止检测' }));
  await act(async () => { finishPoll({ ...job, status: 'completed', report_id: 'finished-report' }); });
  expect(fetchPaperLintReport).not.toHaveBeenCalled();
  await act(async () => { finishCancel({ ...job, status: 'completed', report_id: 'finished-report' }); });
  expect(await screen.findByRole('alertdialog')).toHaveTextContent('检测已完成，无法取消。');
});

it.each(['pending','running'])('does not claim cancellation succeeded when the server still reports %s', async status => {
  vi.mocked(fetchPaperLintJob).mockImplementation(() => new Promise(() => {}));
  vi.mocked(cancelPaperLintJob).mockResolvedValue({ ...job, status } as never);
  restoredCheck();
  fireEvent.click(await screen.findByRole('button', { name: '停止检测' }));
  expect(await screen.findByText('尚未确认停止检测，请稍后重试。')).toBeInTheDocument();
  expect(screen.queryByText('已停止检测，可以重新开始。')).not.toBeInTheDocument();
  expect(localStorage.getItem('paper-lint-active-job:student01')).not.toBeNull();
});

it('holds an already in-flight report response until the pending cancel response can explain completion',async()=>{
  let finishReport!: (value:any)=>void, finishCancel!: (value:any)=>void;
  vi.mocked(fetchPaperLintJob).mockResolvedValue({...job,status:'completed',report_id:'finished-report'});
  vi.mocked(fetchPaperLintReport).mockImplementation(()=>new Promise(resolve=>{finishReport=resolve;}));
  vi.mocked(cancelPaperLintJob).mockImplementation(()=>new Promise(resolve=>{finishCancel=resolve;}));
  restoredCheck();
  await waitFor(()=>expect(fetchPaperLintReport).toHaveBeenCalledTimes(1));
  fireEvent.click(screen.getByRole('button',{name:'停止检测'}));
  await act(async()=>{finishReport({...fixture,id:'finished-report'});});
  expect(screen.queryByText('Saved report opened')).not.toBeInTheDocument();
  await act(async()=>{finishCancel({...job,status:'completed',report_id:'finished-report'});});
  expect(await screen.findByRole('alertdialog')).toHaveTextContent('检测已完成，无法取消。');
});

it('keeps the completion notice and offers a working retry when its report fails to load',async()=>{
  vi.mocked(fetchPaperLintJob).mockImplementation(()=>new Promise(()=>{}));
  vi.mocked(cancelPaperLintJob).mockResolvedValue({...job,status:'completed',report_id:'finished-report'});
  vi.mocked(fetchPaperLintReport).mockRejectedValueOnce(new Error('Network Error')).mockResolvedValue({...fixture,id:'finished-report'});
  restoredCheck();
  fireEvent.click(await screen.findByRole('button',{name:'停止检测'}));
  await screen.findByRole('alertdialog');
  fireEvent.click(screen.getByRole('button',{name:'查看检测报告'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('报告暂时无法加载，请重试。');
  expect(screen.getByRole('alertdialog')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'查看检测报告'}));
  expect(await screen.findByText('Saved report opened')).toBeInTheDocument();
  expect(fetchPaperLintReport).toHaveBeenCalledTimes(2);
});

it('starts a new request after viewing a completed cancellation result later',async()=>{
  vi.mocked(fetchPaperLintJob).mockImplementation(()=>new Promise(()=>{}));
  vi.mocked(cancelPaperLintJob).mockResolvedValue({...job,status:'completed',report_id:'finished-report'});
  render(<MemoryRouter><NormativeCheckPage mode="thirty" /></MemoryRouter>);
  await screen.findByText('已选择全部检测规则');
  fireEvent.change(screen.getByLabelText('上传待审查 PDF'),{target:{files:[new File(['%PDF-1.7'],'check.pdf',{type:'application/pdf'})]}});
  fireEvent.click(screen.getByRole('button',{name:'开始检测'}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'停止检测'})).toBeEnabled());
  const originalRequest=vi.mocked(runReviewPilotPaperLint).mock.calls[0][3];
  fireEvent.click(screen.getByRole('button',{name:'停止检测'}));
  await screen.findByRole('alertdialog');
  fireEvent.click(screen.getByRole('button',{name:'稍后查看'}));
  expect(localStorage.getItem('paper-lint-active-job:student01')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'开始检测'}));
  await waitFor(()=>expect(runReviewPilotPaperLint).toHaveBeenCalledTimes(2));
  expect(vi.mocked(runReviewPilotPaperLint).mock.calls[1][3]).not.toBe(originalRequest);
});
