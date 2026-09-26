import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import ArchiveScanPage from '../src/pages/ArchiveScanPage';
import { fetchCurrentSession } from '../src/api/authSession';
import {
  fetchArchiveCatalog,
  fetchArchiveJob,
  fetchArchiveDocuments,
  fetchArchiveJobs,
  deleteArchiveJob,
  startArchiveJob,
} from '../src/api/archiveScans';
vi.mock('../src/api/authSession', async () => ({
  ...(await vi.importActual('../src/api/authSession')),
  fetchCurrentSession: vi.fn(),
}));
vi.mock('../src/api/archiveScans', () => ({
  fetchArchiveCatalog: vi.fn(),
  fetchArchiveJobs: vi.fn(),
  deleteArchiveJob: vi.fn(),
  startArchiveJob: vi.fn(),
  fetchArchiveJob: vi.fn(),
  fetchArchiveDocuments: vi.fn(),
}));
const rules = [18, 22, 24, 28].map((number) => ({
  rule_id: `sjtu_rule_${number}`,
  title: `规则 ${number}`,
  description: `检测规则 ${number}`,
}));
const admin = {
  id: 'admin',
  username: 'admin',
  role: 'SCHOOL_ADMIN',
  collegeId: null,
  supervisorId: null,
  scope: 'SCHOOL',
};
beforeEach(() => {
  vi.mocked(fetchCurrentSession).mockResolvedValue({ user: admin as never });
  vi.mocked(fetchArchiveCatalog).mockResolvedValue({ rules: rules as never, paper_count: 479 });
  vi.mocked(fetchArchiveJobs).mockResolvedValue({ jobs: [] });
  vi.mocked(deleteArchiveJob).mockResolvedValue(undefined);
  vi.mocked(startArchiveJob).mockResolvedValue({
    job: {
      id: 'job-1',
      total_count: 479,
      completed_count: 0,
      failed_count: 0,
      finding_count: 0,
      status: 'running',
      selected_rule_ids: ['sjtu_rule_18'],
    } as never,
  });
});
const savedJob = {
  id: 'saved',
  total_count: 1,
  completed_count: 1,
  failed_count: 0,
  inconclusive_count: 1,
  finding_count: 0,
  status: 'completed',
  selected_rule_ids: ['sjtu_rule_18', 'sjtu_rule_22'],
  created_at: '2026-09-26T00:00:00Z',
};
function renderPage() {
  return render(
    <MemoryRouter>
      <AuthSessionProvider>
        <ArchiveScanPage />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}
describe('archive scan page', () => {
  it('starts one rule from its card without selecting all rules', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('button', { name: '仅运行规则 18' }));
    await waitFor(() => expect(startArchiveJob).toHaveBeenCalledWith(['sjtu_rule_18']));
  });
  it('labels a paper inconclusive when a later selected rule cannot determine a result', async () => {
    vi.mocked(fetchArchiveJobs).mockResolvedValue({ jobs: [savedJob as never] });
    vi.mocked(fetchArchiveJob).mockResolvedValue({ job: savedJob as never });
    vi.mocked(fetchArchiveDocuments).mockResolvedValue({
      items: [
        {
          id: 'doc',
          job_id: 'saved',
          filename: '论文.pdf',
          relative_path: '硕士/论文.pdf',
          status: 'completed',
          finding_count: 0,
          rule_outcomes: { sjtu_rule_18: 'passed', sjtu_rule_22: 'inconclusive' },
        },
      ] as never,
      total: 1,
      page: 1,
      page_size: 25,
    });
    renderPage();
    expect(await screen.findByRole('link', { name: /论文.pdf/ })).toHaveTextContent('无法判定');
  });
  it('refreshes running job status while an older completed job is selected', async () => {
    const runningJob = { ...savedJob, id: 'running', status: 'running' };
    vi.mocked(fetchArchiveJobs)
      .mockResolvedValueOnce({ jobs: [savedJob, runningJob] as never })
      .mockResolvedValue({ jobs: [savedJob, { ...runningJob, status: 'completed' }] as never });
    vi.mocked(fetchArchiveJob).mockResolvedValue({ job: savedJob as never });
    vi.mocked(fetchArchiveDocuments).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    renderPage();
    const button = await screen.findByRole('button', { name: '仅运行规则 18' });
    expect(button).toBeDisabled();
    await new Promise((resolve) => setTimeout(resolve, 3200));
    await waitFor(() => expect(button).toBeEnabled());
  }, 6500);
  it('clears an old rule filter when switching to a job that did not run that rule', async () => {
    const nextJob = { ...savedJob, id: 'next', selected_rule_ids: ['sjtu_rule_18'] };
    vi.mocked(fetchArchiveJobs).mockResolvedValue({ jobs: [savedJob, nextJob] as never });
    vi.mocked(fetchArchiveJob).mockImplementation(async (id) => ({
      job: (id === 'next' ? nextJob : savedJob) as never,
    }));
    vi.mocked(fetchArchiveDocuments).mockImplementation(async (id, params) => ({
      items:
        id === 'next' && params.rule_id === 'sjtu_rule_22'
          ? []
          : ([
              {
                id: 'doc',
                job_id: id,
                filename: '论文.pdf',
                relative_path: '论文.pdf',
                status: 'completed',
                finding_count: 0,
                rule_outcomes: { sjtu_rule_18: 'passed' },
              },
            ] as never),
      total: 1,
      page: 1,
      page_size: 25,
    }));
    renderPage();
    await screen.findByRole('link', { name: /论文.pdf/ });
    await userEvent.selectOptions(screen.getByRole('combobox', { name: '按规则筛选' }), 'sjtu_rule_22');
    await userEvent.click(screen.getByRole('button', { name: /18 号规则/ }));
    await waitFor(() => expect(screen.getByRole('combobox', { name: '按规则筛选' })).toHaveValue(''));
    expect(await screen.findByRole('link', { name: /论文.pdf/ })).toBeInTheDocument();
  });
  it('confirms deletion of an older saved job and refreshes the list', async () => {
    const older = { ...savedJob, id: 'older', created_at: '2026-09-25T00:00:00Z' };
    vi.mocked(fetchArchiveJobs)
      .mockResolvedValueOnce({ jobs: [savedJob, older] as never })
      .mockResolvedValue({ jobs: [savedJob] as never });
    vi.mocked(fetchArchiveJob).mockResolvedValue({ job: savedJob as never });
    vi.mocked(fetchArchiveDocuments).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    renderPage();
    const deleteButtons = await screen.findAllByRole('button', { name: /删除任务/ });
    expect(deleteButtons).toHaveLength(2);
    await userEvent.click(deleteButtons[1]);
    expect(await screen.findByRole('alertdialog')).toHaveTextContent('删除后无法恢复');
    await userEvent.click(screen.getByRole('button', { name: '取消' }));
    expect(deleteArchiveJob).not.toHaveBeenCalled();
    await userEvent.click(screen.getAllByRole('button', { name: /删除任务/ })[1]);
    await userEvent.click(screen.getByRole('button', { name: '确认删除' }));
    await waitFor(() => expect(deleteArchiveJob).toHaveBeenCalledWith('older'));
    await waitFor(() => expect(screen.getAllByRole('button', { name: /删除任务/ })).toHaveLength(1));
  });

  it('starts selected multiple rules as one job', async () => {
    renderPage();
    await userEvent.click(await screen.findByRole('checkbox', { name: '选择规则 18' }));
    await userEvent.click(screen.getByRole('checkbox', { name: '选择规则 22' }));
    await userEvent.click(screen.getByRole('button', { name: '扫描全部归档论文' }));
    await waitFor(() => expect(startArchiveJob).toHaveBeenCalledWith(['sjtu_rule_18', 'sjtu_rule_22']));
  });
});
