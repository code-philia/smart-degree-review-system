import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import apiClient from '../src/api';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { fetchAiReviewHistory, type AiReviewHistoryRecord } from '../src/api/normativeRules';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return {
    ...actual,
    fetchAiReviewHistory: vi.fn(),
  };
});

const REQ_ID = 'FEAT-AI-REVIEW-HISTORY';
void REQ_ID;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const historyRecords: AiReviewHistoryRecord[] = [
  {
    id: 'review-history-newest',
    user_id: 'student01',
    thesis_title: 'student01 最新辅助评阅论文',
    template_id: 'academic_master',
    total_score: 92,
    result_label: '基础检查通过',
    created_at: '2026-03-02T10:30:00.000Z',
  },
  {
    id: 'review-history-older',
    user_id: 'student01',
    thesis_title: 'student01 较早辅助评阅论文',
    template_id: 'professional_master',
    total_score: 40,
    result_label: '需修改',
    created_at: '2026-03-01T09:00:00.000Z',
  },
];

function renderRoute(initialPath = '/ai-review/history') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-AI-REVIEW-HISTORY frontend history route and client contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchAiReviewHistory).mockReset();
  });

  it('FEAT-AI-REVIEW-HISTORY:FRONTEND:AUTH:001 prompts anonymous users to login and does not fetch history records', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: 'AI 智能评阅' })).toBeInTheDocument();
    expect(screen.getByText('请先登录后查看本人辅助评阅历史记录。')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(fetchAiReviewHistory).not.toHaveBeenCalled();
    expect(screen.queryByText('student01 最新辅助评阅论文')).not.toBeInTheDocument();
  });

  it('FEAT-AI-REVIEW-HISTORY:FRONTEND:SCENARIO:001 renders API-provided records in order with result-page entry links', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchAiReviewHistory).mockResolvedValue(historyRecords);

    renderRoute();

    expect(await screen.findByRole('heading', { name: '智能评阅记录' })).toBeInTheDocument();
    await waitFor(() => expect(fetchAiReviewHistory).toHaveBeenCalledTimes(1));
    expect(screen.getByText('共 2 条记录')).toBeInTheDocument();
    const rows = screen.getAllByRole('row');
    expect(rows).toHaveLength(3);

    const newestRow = rows[1];
    const olderRow = rows[2];
    expect(within(newestRow).getByText('1')).toBeInTheDocument();
    expect(within(newestRow).getByText('student01 最新辅助评阅论文')).toBeInTheDocument();
    expect(within(newestRow).getByText('academic_master')).toBeInTheDocument();
    expect(within(newestRow).getByText('92')).toBeInTheDocument();
    expect(within(newestRow).getByText('基础检查通过')).toBeInTheDocument();
    expect(within(newestRow).getByText('2026-03-02 10:30:00.000')).toBeInTheDocument();
    expect(within(newestRow).getByRole('link', { name: '查看结果' })).toHaveAttribute(
      'href',
      '/ai-review/results/review-history-newest',
    );

    expect(within(olderRow).getByText('2')).toBeInTheDocument();
    expect(within(olderRow).getByText('student01 较早辅助评阅论文')).toBeInTheDocument();
    expect(within(olderRow).getByText('professional_master')).toBeInTheDocument();
    expect(within(olderRow).getByText('40')).toBeInTheDocument();
    expect(within(olderRow).getByText('需修改')).toBeInTheDocument();
    expect(within(olderRow).getByRole('link', { name: '查看结果' })).toHaveAttribute(
      'href',
      '/ai-review/results/review-history-older',
    );
    expect(screen.queryByText('截图示例论文')).not.toBeInTheDocument();
  });

  it('FEAT-AI-REVIEW-HISTORY:FRONTEND:EMPTY:001 shows an explicit empty state instead of hardcoded sample rows', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchAiReviewHistory).mockResolvedValue([]);

    renderRoute();

    expect(await screen.findByRole('heading', { name: '智能评阅记录' })).toBeInTheDocument();
    expect(await screen.findByText('暂无辅助评阅历史记录。')).toBeInTheDocument();
    expect(screen.getByText('共 0 条记录')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('FEAT-AI-REVIEW-HISTORY:FRONTEND:ERROR:001 shows API errors explicitly instead of fallback rows', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchAiReviewHistory).mockRejectedValue(new Error('辅助评阅历史加载失败'));

    renderRoute();

    expect(await screen.findByRole('alert')).toHaveTextContent('辅助评阅历史加载失败');
    expect(screen.queryByText('student01 最新辅助评阅论文')).not.toBeInTheDocument();
  });

  it('FEAT-AI-REVIEW-HISTORY:FRONTEND:CLIENT:001 fetches history through the shared Axios client without local fallback data', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: { records: historyRecords } });
    const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');

    const records = await actual.fetchAiReviewHistory();

    expect(getSpy).toHaveBeenCalledWith('/normative/ai-review-runs');
    expect(records).toBe(historyRecords);
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();

    getSpy.mockRestore();
  });
});
