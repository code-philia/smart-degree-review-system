import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { IncrementalRerunDialog } from '../src/components/paperLint/IncrementalRerunDialog';
import { fetchPaperLintDailyQuota, rerunPaperLintReport } from '../src/api/paperLint';
vi.mock('../src/api/paperLint', async () => ({ ...await vi.importActual('../src/api/paperLint'), fetchPaperLintDailyQuota: vi.fn(), rerunPaperLintReport: vi.fn() }));
afterEach(() => { localStorage.clear(); vi.clearAllMocks(); vi.unstubAllGlobals(); });
const report = { id: 'old-report', source_filename: 'original.pdf', selected_rule_ids: ['sjtu_rule_18', 'sjtu_rule_22'], result: { rule_runs: [
  { rule_id: 'sjtu_rule_18', execution_status: 'completed', outcome: 'issues_found', findings: [] },
  { rule_id: 'sjtu_rule_22', execution_status: 'error', outcome: 'inconclusive', findings: [] },
] } } as any;
const rules = [
  { rule_id: 'sjtu_rule_18', title: '公式引用', available: true },
  { rule_id: 'sjtu_rule_22', title: '文献引用', available: true },
  { rule_id: 'sjtu_rule_24', title: '未引用文献', available: true },
] as any;
function show() { render(<MemoryRouter initialEntries={['/report']}><Routes>
  <Route path="/report" element={<IncrementalRerunDialog report={report} rules={rules} initiallyOpen />} />
  <Route path="/paper-upload" element={<p>已进入检测进度页</p>} />
</Routes></MemoryRouter>); }
it('reuses the original PDF, submits only added rules, and restores the queued job on HTTP origins', async () => {
  vi.stubGlobal('crypto', {});
  vi.mocked(rerunPaperLintReport).mockResolvedValue({ job_id: 'new-job', user_id: 'student', source_filename: 'original.pdf',
    selected_rule_ids: ['sjtu_rule_18','sjtu_rule_22','sjtu_rule_24'], status: 'pending', queue_position: 2 } as any);
  show();
  expect(screen.getByText('复用已完成结果')).toBeVisible();
  expect(screen.getByText('本次补跑')).toBeVisible();
  expect(screen.queryByLabelText('上传待审查 PDF')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('checkbox', { name: /未引用文献/ }));
  fireEvent.click(screen.getByRole('button', { name: '开始增量检测（2 项）' }));
  expect(await screen.findByText('已进入检测进度页')).toBeInTheDocument();
  expect(rerunPaperLintReport).toHaveBeenCalledWith('old-report', ['sjtu_rule_24'], expect.stringMatching(/^rerun-/));
  expect(JSON.parse(localStorage.getItem('paper-lint-active-job:student')!)).toMatchObject({
    jobId: 'new-job', filename: 'original.pdf', selectedRuleIds: ['sjtu_rule_18','sjtu_rule_22','sjtu_rule_24'],
  });
});
it('retains the request identifier when retrying a failed submission', async () => {
  vi.mocked(rerunPaperLintReport).mockRejectedValue(new Error('连接中断'));
  show();
  const button = screen.getByRole('button', { name: '开始增量检测（1 项）' });
  fireEvent.click(button); expect(await screen.findByRole('alert')).toHaveTextContent('连接中断');
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  await waitFor(() => expect(rerunPaperLintReport).toHaveBeenCalledTimes(2));
  expect(vi.mocked(rerunPaperLintReport).mock.calls[1][2]).toBe(vi.mocked(rerunPaperLintReport).mock.calls[0][2]);
});

it('also blocks incremental reruns once three reports have been generated', async () => {
 vi.mocked(fetchPaperLintDailyQuota).mockResolvedValue({limited:true,limit:3,used:3,reserved:0,remaining:0,day:'2026-11-12',resets_at:'2026-11-12T16:00:00Z',server_time:'2026-11-12T02:00:00Z',timezone:'Asia/Shanghai'});
 show(); expect(await screen.findByText('检测次数已用完')).toBeVisible();
 expect(screen.getByRole('button',{name:'开始增量检测（1 项）'})).toBeDisabled();
 expect(rerunPaperLintReport).not.toHaveBeenCalled();
});

it('recovers a reserved rerun after a lost response without creating a new request', async () => {
 const quota={limited:true,limit:3,used:2,reserved:0,remaining:1,day:'2026-11-12',resets_at:'2026-11-12T16:00:00Z',server_time:'2026-11-12T02:00:00Z',timezone:'Asia/Shanghai'};
 vi.mocked(fetchPaperLintDailyQuota).mockResolvedValue(quota);
 vi.mocked(rerunPaperLintReport).mockImplementationOnce(async()=>{
   vi.mocked(fetchPaperLintDailyQuota).mockResolvedValue({...quota,reserved:1,remaining:0});
   throw Object.assign(new Error('Network Error'),{isAxiosError:true});
 }).mockResolvedValueOnce({job_id:'retry-job',user_id:'student',source_filename:'original.pdf',status:'pending'} as any);
 show(); await screen.findByText('剩余 1 / 3 次');
 const start=screen.getByRole('button',{name:'开始增量检测（1 项）'});fireEvent.click(start);
 expect(await screen.findByText('可用次数已暂占')).toBeVisible();
 await waitFor(()=>expect(start).toBeEnabled());fireEvent.click(start);
 expect(await screen.findByText('已进入检测进度页')).toBeVisible();
 expect(vi.mocked(rerunPaperLintReport).mock.calls[1][2]).toBe(vi.mocked(rerunPaperLintReport).mock.calls[0][2]);
});
