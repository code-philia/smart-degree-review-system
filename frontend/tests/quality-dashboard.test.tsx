import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import QualityDashboardPage from '../src/pages/QualityDashboardPage';
import {
  fetchQualityDashboard,
  type QualityDashboardResponse,
} from '../src/api/normativeRules';

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return {
    ...actual,
    fetchQualityDashboard: vi.fn(),
  };
});

const REQ_ID = 'FEAT-QUALITY-DASHBOARD';
void REQ_ID;

const scenarioDashboard: QualityDashboardResponse = {
  filters: { from: '2026-08-04', to: '2026-08-04', latest_only: false },
  sample_count: 1,
  metrics: [
    { key: 'normative', label: '规范分', average_score: 79, sample_count: 1, missing_count: 0, distribution: [{ range: '70-79', count: 1 }] },
    { key: 'originality', label: '原创参考分', average_score: 73, sample_count: 1, missing_count: 0, distribution: [{ range: '70-79', count: 1 }] },
    { key: 'innovation', label: '创新参考分', average_score: 88, sample_count: 1, missing_count: 0, distribution: [{ range: '80-89', count: 1 }] },
    { key: 'review_base', label: '评阅基础分', average_score: null, sample_count: 0, missing_count: 1, distribution: [] },
  ],
  students: [
    {
      student_id: 'student01',
      student_name: '张三',
      scores: {
        normative: 79,
        originality: 73,
        innovation: 88,
        review_base: null,
      },
    },
  ],
  generated_at: '2026-08-04T12:00:00.000Z',
};

function renderPage() {
  return render(<QualityDashboardPage />);
}

describe('FEAT-QUALITY-DASHBOARD quality dashboard UI contract', () => {
  beforeEach(() => {
    vi.mocked(fetchQualityDashboard).mockReset();
  });

  it('FEAT-QUALITY-DASHBOARD:UI:ROUTE:001 mounts /quality-dashboard through the existing App route tree', () => {
    render(
      <MemoryRouter initialEntries={['/quality-dashboard']}>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole('banner')).toHaveTextContent('群体质量仪表盘');
    expect(screen.getByRole('button', { name: '生成仪表盘' })).toBeInTheDocument();
    expect(screen.getByText('请选择筛选条件后生成群体质量仪表盘')).toBeInTheDocument();
    expect(fetchQualityDashboard).not.toHaveBeenCalled();
  });

  it('FEAT-QUALITY-DASHBOARD:UI:FILTERS:001 starts empty and sends selected ledger filters on manual refresh without fallback rows', async () => {
    vi.mocked(fetchQualityDashboard).mockResolvedValueOnce({ ...scenarioDashboard, sample_count: 0, students: [] });
    const user = userEvent.setup();

    renderPage();

    expect(screen.getByText('请选择筛选条件后生成群体质量仪表盘')).toBeInTheDocument();
    expect(screen.queryByText('张三')).not.toBeInTheDocument();

    const dateInputs = screen.getAllByDisplayValue('');
    await user.type(dateInputs[0], '2026-08-04');
    await user.type(dateInputs[1], '2026-08-04');
    await user.type(screen.getByPlaceholderText('姓名或学号'), 'student01');
    await user.selectOptions(screen.getByLabelText('类型'), 'normative');
    await user.click(screen.getByRole('button', { name: '生成仪表盘' }));

    await waitFor(() => expect(fetchQualityDashboard).toHaveBeenCalledTimes(1));
    expect(fetchQualityDashboard).toHaveBeenCalledWith({
      from: '2026-08-04',
      to: '2026-08-04',
      student: 'student01',
      detection_type: 'normative',
      latest_only: true,
    });
    expect(screen.getByText('当前筛选条件下暂无学生质量数据')).toBeInTheDocument();
  });

  it('FEAT-QUALITY-DASHBOARD:UI:SCENARIO:001 renders formula scores and displays missing review base as 暂无数据 instead of zero', async () => {
    vi.mocked(fetchQualityDashboard).mockResolvedValueOnce(scenarioDashboard);
    const user = userEvent.setup();

    renderPage();
    await user.click(screen.getByRole('button', { name: '生成仪表盘' }));

    await waitFor(() => expect(fetchQualityDashboard).toHaveBeenCalledTimes(1));
    expect(screen.getByText('样本数').nextSibling).toHaveTextContent('1');

    for (const [label, value] of [
      ['规范分', '79.0'],
      ['原创参考分', '73.0'],
      ['创新参考分', '88.0'],
    ] as const) {
      const metricCard = screen.getAllByText(label)[0].closest('article');
      expect(metricCard).not.toBeNull();
      expect(within(metricCard as HTMLElement).getByText(value)).toBeInTheDocument();
    }

    const reviewMetricCard = screen.getAllByText('评阅基础分')[0].closest('article');
    expect(reviewMetricCard).not.toBeNull();
    expect(within(reviewMetricCard as HTMLElement).getByText('暂无数据')).toBeInTheDocument();
    expect(within(reviewMetricCard as HTMLElement).getByText('有效 0，缺失 1')).toBeInTheDocument();
    expect(within(reviewMetricCard as HTMLElement).queryByText('0.0')).not.toBeInTheDocument();

    const table = screen.getByRole('table');
    const studentRow = within(table).getByRole('row', { name: /张三/ });
    expect(within(studentRow).getByText('79.0')).toBeInTheDocument();
    expect(within(studentRow).getByText('73.0')).toBeInTheDocument();
    expect(within(studentRow).getByText('88.0')).toBeInTheDocument();
    expect(within(studentRow).getByText('暂无数据')).toBeInTheDocument();
  });

  it('FEAT-QUALITY-DASHBOARD:UI:ERROR:001 shows backend error state without substituting hardcoded dashboard data', async () => {
    vi.mocked(fetchQualityDashboard).mockRejectedValueOnce(new Error('质量仪表盘加载失败'));

    renderPage();
    await userEvent.click(screen.getByRole('button', { name: '生成仪表盘' }));

    expect(await screen.findByText('质量仪表盘加载失败')).toBeInTheDocument();
    expect(screen.queryByText('样本数')).not.toBeInTheDocument();
    expect(screen.queryByText('张三')).not.toBeInTheDocument();
  });
});
