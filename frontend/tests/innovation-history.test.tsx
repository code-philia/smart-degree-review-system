import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  downloadInnovationReportJson,
  fetchInnovationHistory,
  type InnovationHistoryRecord,
} from '../src/api/normativeRules';
import apiClient from '../src/api';

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
    downloadInnovationReportJson: vi.fn(),
    fetchInnovationHistory: vi.fn(),
  };
});

const reqId = 'FEAT-INNOVATION-HISTORY';
void reqId;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const historyRecords: InnovationHistoryRecord[] = [
  {
    id: 'student01-innovation-new',
    user_id: 'student01',
    thesis_title: 'student01 第二次创新性评估',
    degree_type: 'doctoral',
    total_score: 88,
    grade_label: '优秀',
    created_at: '2026-08-04T11:00:00.000Z',
  },
  {
    id: 'student01-innovation-old',
    user_id: 'student01',
    thesis_title: 'student01 第一次创新性评估',
    degree_type: 'master',
    total_score: 72,
    grade_label: '中等',
    created_at: '2026-08-04T09:00:00.000Z',
  },
];

function renderRoute(initialPath = '/innovation-history') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-INNOVATION-HISTORY frontend page, route, and client contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchInnovationHistory).mockReset();
    vi.mocked(downloadInnovationReportJson).mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('FEAT-INNOVATION-HISTORY:UI:AUTHZ:001 renders a login-required state and does not fetch protected history for anonymous users', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: '创新性分析历史记录' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后查看本人创新性评估历史/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(fetchInnovationHistory).not.toHaveBeenCalled();
  });

  it('FEAT-INNOVATION-HISTORY:UI:SCENARIO:001 displays authenticated student history with newest record first and report preview links', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchInnovationHistory).mockResolvedValue(historyRecords);

    renderRoute();

    expect(await screen.findByRole('heading', { name: '创新性量表评估' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '发起评估' })).toHaveAttribute('href', '/innovation-assessment');
    await waitFor(() => expect(fetchInnovationHistory).toHaveBeenCalledTimes(1));
    expect(screen.getByText('共 2 条记录')).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '论文题目' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '学历层次' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '综合分' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '等级' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: '生成时间' })).toBeInTheDocument();

    const rows = screen.getAllByRole('row');
    expect(rows[1]).toHaveTextContent('student01 第二次创新性评估');
    expect(rows[1]).toHaveTextContent('博士');
    expect(rows[1]).toHaveTextContent('88');
    expect(rows[1]).toHaveTextContent('优秀');
    expect(rows[1]).toHaveTextContent('2026-08-04 11:00:00.000');
    expect(rows[2]).toHaveTextContent('student01 第一次创新性评估');
    expect(rows[2]).toHaveTextContent('硕士');
    expect(rows[2]).toHaveTextContent('72');
    expect(rows[2]).toHaveTextContent('中等');
    expect(screen.getAllByRole('link', { name: '报告预览' })[0]).toHaveAttribute(
      'href',
      '/innovation-assessments/student01-innovation-new',
    );
  });

  it('FEAT-INNOVATION-HISTORY:UI:SEARCH:001 filters by thesis title through the toolbar search without fabricating rows', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchInnovationHistory).mockResolvedValue(historyRecords);
    const user = userEvent.setup();

    renderRoute();

    await screen.findByText('student01 第二次创新性评估');
    await user.type(screen.getByPlaceholderText('请输入论文题目搜索'), '第二次');
    await user.click(screen.getByRole('button', { name: '搜索' }));

    expect(screen.getByText('共 1 条记录')).toBeInTheDocument();
    expect(screen.getByText('student01 第二次创新性评估')).toBeInTheDocument();
    expect(screen.queryByText('student01 第一次创新性评估')).not.toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText('请输入论文题目搜索'));
    await user.type(screen.getByPlaceholderText('请输入论文题目搜索'), '不存在的论文题目');
    await user.click(screen.getByRole('button', { name: '搜索' }));

    expect(screen.getByText('共 0 条记录')).toBeInTheDocument();
    expect(screen.getByText('暂无创新性评估历史记录。')).toBeInTheDocument();
  });

  it('FEAT-INNOVATION-HISTORY:API-CLIENT:001 uses the shared Axios client for the same-origin owned history endpoint', async () => {
    const getSpy = vi.spyOn(apiClient, 'get');
    getSpy.mockResolvedValueOnce({ data: { records: historyRecords } });

    const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
    await expect(actual.fetchInnovationHistory()).resolves.toEqual(historyRecords);

    expect(getSpy).toHaveBeenCalledWith('/normative/innovation-assessments');
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
