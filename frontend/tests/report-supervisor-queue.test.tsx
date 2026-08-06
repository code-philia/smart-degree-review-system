import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  fetchSupervisorReviewQueue,
  fetchSupervisorReviewQueueBadge,
  type SupervisorReviewQueueResponse,
} from '../src/api/reportSupervisorQueue';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/reportSupervisorQueue', async () => {
  const actual = await vi.importActual<typeof import('../src/api/reportSupervisorQueue')>(
    '../src/api/reportSupervisorQueue',
  );
  return {
    ...actual,
    fetchSupervisorReviewQueue: vi.fn(),
    fetchSupervisorReviewQueueBadge: vi.fn(),
  };
});

const REQ_ID = 'FEAT-REPORT-SUPERVISOR-QUEUE';
void REQ_ID;

const supervisorUser: AuthenticatedUser = {
  id: 'supervisor01',
  username: 'supervisor01',
  role: 'SUPERVISOR',
  collegeId: 'college01',
  scope: 'COLLEGE',
};

const queueResponse: SupervisorReviewQueueResponse = {
  unread_count: 2,
  records: [
    {
      todo_id: 'todo-supervisor01-newer',
      submission_id: 'submission-supervisor01-newer',
      student_id: 'student01',
      assignee_id: 'supervisor01',
      source_type: 'normative',
      report_id: 'normative-supervisor01-newer',
      submission_status: 'submitted_pending_review',
      todo_status: 'pending',
      title: '规范报告待批阅',
      created_at: '2026-08-05T12:00:00.000Z',
    },
    {
      todo_id: 'todo-supervisor01-older',
      submission_id: 'submission-supervisor01-older',
      student_id: 'student01',
      assignee_id: 'supervisor01',
      source_type: 'ai_review',
      report_id: 'ai-review-supervisor01-older',
      submission_status: 'submitted_pending_review',
      todo_status: 'done',
      title: 'AI 评阅报告已完成',
      created_at: '2026-08-05T11:00:00.000Z',
    },
  ],
};

function renderRoute(initialPath = '/supervisor-review-queue') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-REPORT-SUPERVISOR-QUEUE frontend page and client contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchSupervisorReviewQueue).mockReset();
    vi.mocked(fetchSupervisorReviewQueueBadge).mockReset();
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:UI:SCENARIO:001 renders runtime supervisor01 records and unread count without fake or foreign rows', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: supervisorUser });
    vi.mocked(fetchSupervisorReviewQueue).mockResolvedValue(queueResponse);

    renderRoute();

    expect(await screen.findByRole('heading', { name: '待批阅任务' })).toBeInTheDocument();
    expect(screen.getByText('未完成待办').closest('div')).toHaveTextContent('2');
    const table = await screen.findByRole('table');
    expect(within(table).getAllByText('student01').length).toBeGreaterThan(0);
    expect(within(table).getByText('normative-supervisor01-newer')).toBeInTheDocument();
    expect(within(table).getByText('ai-review-supervisor01-older')).toBeInTheDocument();
    expect(screen.queryByText(/supervisor02|student02|示例|demo/i)).not.toBeInTheDocument();
    expect(fetchSupervisorReviewQueue).toHaveBeenCalledWith({});
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:UI:FILTERS:001 refetches through the typed client when student, report type, or status filters change', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: supervisorUser });
    vi.mocked(fetchSupervisorReviewQueue).mockResolvedValue(queueResponse);
    const user = userEvent.setup();

    renderRoute();
    await screen.findByText('normative-supervisor01-newer');

    await user.type(screen.getByPlaceholderText('学生账号'), 'student01');
    await user.selectOptions(screen.getByLabelText('报告类型'), 'normative');
    await user.selectOptions(screen.getByLabelText('状态'), 'pending');

    await waitFor(() =>
      expect(fetchSupervisorReviewQueue).toHaveBeenLastCalledWith({
        student_id: 'student01',
        source_type: 'normative',
        status: 'pending',
      }),
    );
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:UI:EMPTY-ERROR:001 renders explicit empty and error states from the real API path', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: supervisorUser });
    vi.mocked(fetchSupervisorReviewQueue).mockResolvedValueOnce({ records: [], unread_count: 0 });

    const { unmount } = renderRoute();
    expect(await screen.findByText('暂无待批阅任务。')).toBeInTheDocument();
    expect(screen.getByText('未完成待办').closest('div')).toHaveTextContent('0');
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    unmount();

    vi.mocked(fetchSupervisorReviewQueue).mockRejectedValueOnce(new Error('403'));
    renderRoute();
    expect(await screen.findByText('待批阅任务加载失败，请确认导师身份后重试')).toBeInTheDocument();
    expect(screen.queryByText(/已加载示例|demo/i)).not.toBeInTheDocument();
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:API-CLIENT:001 uses the shared Axios client for queue and badge endpoints with query params', async () => {
    const getSpy = vi.spyOn(apiClient, 'get');
    getSpy.mockResolvedValueOnce({ data: queueResponse }).mockResolvedValueOnce({ data: { unread_count: 2 } });

    const actual = await vi.importActual<typeof import('../src/api/reportSupervisorQueue')>(
      '../src/api/reportSupervisorQueue',
    );
    await expect(
      actual.fetchSupervisorReviewQueue({ student_id: 'student01', source_type: 'normative', status: 'pending' }),
    ).resolves.toEqual(queueResponse);
    await expect(actual.fetchSupervisorReviewQueueBadge()).resolves.toEqual({ unread_count: 2 });

    expect(getSpy).toHaveBeenNthCalledWith(1, '/normative/supervisor-review-queue', {
      params: { student_id: 'student01', source_type: 'normative', status: 'pending' },
    });
    expect(getSpy).toHaveBeenNthCalledWith(2, '/normative/supervisor-review-queue/badge');
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
