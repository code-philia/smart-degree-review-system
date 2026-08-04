import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { calculateInnovationScore, type InnovationScoreResponse } from '../src/api/normativeRules';

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
    calculateInnovationScore: vi.fn(),
  };
});

const reqId = 'FEAT-INNOVATION-SCORING-MODEL';
void reqId;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const scenarioPayload = {
  degree_type: 'master' as const,
  levels: {
    research_topic: 5,
    research_method: 4,
    research_content: 4,
    research_conclusion: 3,
    application_value: 4,
  },
};

const scenarioReport: InnovationScoreResponse = {
  degree_type: 'master',
  total_score: 80,
  grade_label: '良好',
  formula: '维度原始分=等级×20；综合分=各维度原始分×权重之和。硕士权重依次为 20%、20%、25%、20%、15%。',
  input: scenarioPayload,
  dimensions: [
    { key: 'research_topic', label: '研究选题', level: 5, raw_score: 100, weight: 0.2, weighted_score: 20 },
    { key: 'research_method', label: '研究方法', level: 4, raw_score: 80, weight: 0.2, weighted_score: 16 },
    { key: 'research_content', label: '研究内容', level: 4, raw_score: 80, weight: 0.25, weighted_score: 20 },
    { key: 'research_conclusion', label: '研究结论', level: 3, raw_score: 60, weight: 0.2, weighted_score: 12 },
    { key: 'application_value', label: '应用价值', level: 4, raw_score: 80, weight: 0.15, weighted_score: 12 },
  ],
};

function renderRoute(initialPath = '/innovation-scoring') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-INNOVATION-SCORING-MODEL frontend route and transparent report contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(calculateInnovationScore).mockReset();
  });

  it('renders /innovation-scoring under shared auth and submits the master scenario through the API client', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(calculateInnovationScore).mockResolvedValue(scenarioReport);
    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByRole('heading', { name: '创新性评分' })).toBeInTheDocument();
    expect(screen.getByText(/当前登录用户：student01（STUDENT）/)).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText('学位类型'), 'master');
    await user.selectOptions(screen.getByLabelText('研究选题等级'), '5');
    await user.selectOptions(screen.getByLabelText('研究方法等级'), '4');
    await user.selectOptions(screen.getByLabelText('研究内容等级'), '4');
    await user.selectOptions(screen.getByLabelText('研究结论等级'), '3');
    await user.selectOptions(screen.getByLabelText('应用价值等级'), '4');
    await user.click(screen.getByRole('button', { name: '计算创新性分数' }));

    await waitFor(() => expect(calculateInnovationScore).toHaveBeenCalledWith(scenarioPayload));
    expect(await screen.findByRole('heading', { name: '创新性评分报告' })).toBeInTheDocument();
    expect(screen.getByText('80 分')).toBeInTheDocument();
    expect(screen.getByText('良好')).toBeInTheDocument();
    expect(screen.getByText(/硕士权重依次为 20%、20%、25%、20%、15%/)).toBeInTheDocument();

    const table = screen.getByRole('table', { name: '创新性评分明细' });
    for (const dimension of scenarioReport.dimensions) {
      const row = within(table).getByText(dimension.label).closest('tr');
      expect(row).toBeTruthy();
      expect(within(row as HTMLTableRowElement).getByText(String(dimension.level))).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(String(dimension.raw_score))).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(`${dimension.weight * 100}%`)).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(String(dimension.weighted_score))).toBeInTheDocument();
    }
  });

  it('renders a login prompt for anonymous users and does not submit local-only scoring', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: '创新性评分' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后计算创新性分数/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(screen.queryByRole('button', { name: '计算创新性分数' })).not.toBeInTheDocument();
    expect(calculateInnovationScore).not.toHaveBeenCalled();
  });

  it('shows an explicit error state and clears stale reports when backend scoring fails', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(calculateInnovationScore)
      .mockResolvedValueOnce(scenarioReport)
      .mockRejectedValueOnce(new Error('评分服务暂不可用'));
    const user = userEvent.setup();

    renderRoute();

    await user.click(await screen.findByRole('button', { name: '计算创新性分数' }));
    expect(await screen.findByRole('heading', { name: '创新性评分报告' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '计算创新性分数' }));

    expect(await screen.findByText('评分服务暂不可用')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '创新性评分报告' })).not.toBeInTheDocument();
  });
});
