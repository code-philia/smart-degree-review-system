import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { createReportSubmissions, type CreateReportSubmissionResponse } from '../src/api/reportSubmissions';
import {
  fetchAiReviewHistory,
  fetchDuplicationHistory,
  fetchInnovationHistory,
  fetchNormativeDetectionHistory,
} from '../src/api/normativeRules';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/reportSubmissions', async () => {
  const actual = await vi.importActual<typeof import('../src/api/reportSubmissions')>('../src/api/reportSubmissions');
  return {
    ...actual,
    createReportSubmissions: vi.fn(),
  };
});

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return {
    ...actual,
    fetchAiReviewHistory: vi.fn(),
    fetchDuplicationHistory: vi.fn(),
    fetchInnovationHistory: vi.fn(),
    fetchNormativeDetectionHistory: vi.fn(),
  };
});

const REQ_ID = 'FEAT-REPORT-STUDENT-SUBMIT';
void REQ_ID;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const runtimeNormativeReport = {
  id: 'normative-ui-001',
  user_id: 'student01',
  status: 'completed',
  source_type: 'file',
  source_filename: 'student01-规范检测报告.txt',
  original_text: '摘要\n关键词\n结论',
  rule_snapshot: [],
  issues: [],
  severity_counts: { high: 0, medium: 0, low: 0 },
  created_at: '2026-08-05T09:00:00.000Z',
};

const submissionResponse: CreateReportSubmissionResponse = {
  batch_id: 'batch-ui-001',
  submissions: [
    {
      id: 'submission-ui-001',
      batch_id: 'batch-ui-001',
      student_id: 'student01',
      supervisor_id: 'supervisor01',
      source_type: 'normative',
      report_id: 'normative-ui-001',
      status: 'submitted_pending_review',
      created_at: '2026-08-05T10:00:00.000Z',
    },
  ],
  todos: [
    {
      id: 'todo-ui-001',
      submission_id: 'submission-ui-001',
      assignee_id: 'supervisor01',
      actor_id: 'student01',
      status: 'pending',
      title: '报告待批阅',
      created_at: '2026-08-05T10:00:00.000Z',
    },
  ],
};

function renderRoute(initialPath = '/student-report-submissions') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-REPORT-STUDENT-SUBMIT frontend page and client contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(createReportSubmissions).mockReset();
    vi.mocked(fetchNormativeDetectionHistory).mockReset();
    vi.mocked(fetchDuplicationHistory).mockReset();
    vi.mocked(fetchInnovationHistory).mockReset();
    vi.mocked(fetchAiReviewHistory).mockReset();
    vi.mocked(fetchNormativeDetectionHistory).mockResolvedValue([]);
    vi.mocked(fetchDuplicationHistory).mockResolvedValue([]);
    vi.mocked(fetchInnovationHistory).mockResolvedValue([]);
    vi.mocked(fetchAiReviewHistory).mockResolvedValue([]);
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:UI:EMPTY:001 renders the student ledger shell with no fake report rows and disables 推送报告 with no selection', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });

    renderRoute();

    expect(await screen.findByRole('heading', { name: '学生报告提交与批阅结果台账' })).toBeInTheDocument();
    expect(screen.getByText('报告状态流转：')).toBeInTheDocument();
    expect(screen.getByText('暂无已加载的可提交报告。')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '推送报告' })).toBeDisabled();
    expect(screen.queryByText(/student01-规范报告|示例报告|demo/i)).not.toBeInTheDocument();
    expect(createReportSubmissions).not.toHaveBeenCalled();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:UI:SCENARIO:001 submits selected runtime report ids and displays the backend-created batch summary', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchNormativeDetectionHistory).mockResolvedValue([runtimeNormativeReport]);
    vi.mocked(createReportSubmissions).mockResolvedValue(submissionResponse);
    const user = userEvent.setup();

    renderRoute();

    const reportCheckbox = await screen.findByRole('checkbox', { name: /规范检测.*normative-ui-001/ });
    await user.click(reportCheckbox);
    await user.click(screen.getByRole('button', { name: '推送报告' }));

    await waitFor(() =>
      expect(createReportSubmissions).toHaveBeenCalledWith({
        reports: [{ source_type: 'normative', report_id: 'normative-ui-001' }],
      }),
    );
    expect(await screen.findByText(/已创建批次 batch-ui-001/)).toBeInTheDocument();
    expect(screen.getByText(/待批阅记录 1 条/)).toBeInTheDocument();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:UI:ERROR:001 renders the backend failure state instead of a fake success message', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchNormativeDetectionHistory).mockResolvedValue([runtimeNormativeReport]);
    vi.mocked(createReportSubmissions).mockRejectedValue(new Error('403'));
    const user = userEvent.setup();

    renderRoute();

    await user.click(await screen.findByRole('checkbox', { name: /规范检测.*normative-ui-001/ }));
    await user.click(screen.getByRole('button', { name: '推送报告' }));

    expect(await screen.findByText('报告提交失败，请确认所选报告已完成且属于本人')).toBeInTheDocument();
    expect(screen.queryByText(/已创建批次/)).not.toBeInTheDocument();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:API-CLIENT:001 uses the shared Axios client for the same-origin report-submission endpoint', async () => {
    const postSpy = vi.spyOn(apiClient, 'post');
    postSpy.mockResolvedValueOnce({ data: submissionResponse });

    const actual = await vi.importActual<typeof import('../src/api/reportSubmissions')>('../src/api/reportSubmissions');
    await expect(
      actual.createReportSubmissions({
        reports: [{ source_type: 'normative', report_id: 'normative-ui-001' }],
      }),
    ).resolves.toEqual(submissionResponse);

    expect(postSpy).toHaveBeenCalledWith('/normative/report-submissions', {
      reports: [{ source_type: 'normative', report_id: 'normative-ui-001' }],
    });
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
