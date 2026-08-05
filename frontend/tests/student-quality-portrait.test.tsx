import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import StudentQualityPortraitPage from '../src/pages/StudentQualityPortraitPage';
import {
  fetchStudentQualityPortrait,
  type StudentQualityPortraitResponse,
} from '../src/api/normativeRules';

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return {
    ...actual,
    fetchStudentQualityPortrait: vi.fn(),
  };
});

const REQ_ID = 'FEAT-STUDENT-QUALITY-PORTRAIT';
void REQ_ID;

const completePortrait: StudentQualityPortraitResponse = {
  student: {
    student_id: 'student01',
    student_number: 'student01',
    student_name: '张三',
    college_id: 'college01',
    college_name: '计算机学院',
    supervisor_id: 'supervisor01',
    supervisor_name: '李导师',
    student_category: '硕士研究生',
    thesis_title: '单学生本地质量画像研究',
  },
  metrics: [
    { key: 'normative', label: '规范分', score: 80, source_record_id: 'normative-latest', source_type: 'normative', source_label: '最新规范性检测', source_created_at: '2026-08-04T10:00:00.000Z', detail_url: '/normative-reports/normative-latest' },
    { key: 'originality', label: '原创参考分', score: 90, source_record_id: 'duplication-latest', source_type: 'duplication', source_label: '最新论文查重', source_created_at: '2026-08-04T10:30:00.000Z', detail_url: '/duplication-history/duplication-latest' },
    { key: 'innovation', label: '创新参考分', score: 70, source_record_id: 'innovation-latest', source_type: 'innovation', source_label: '最新创新性评价', source_created_at: '2026-08-04T11:00:00.000Z', detail_url: '/innovation-assessments/innovation-latest' },
    { key: 'review_base', label: '评阅基础分', score: 80, source_record_id: 'review-latest', source_type: 'ai_review', source_label: '最新 AI 智能评阅', source_created_at: '2026-08-04T11:30:00.000Z', detail_url: '/ai-review/results/review-latest' },
  ],
  overall_score: 80,
  completeness: { complete: true, missing_metric_keys: [], missing_metric_labels: [] },
  generated_at: '2026-08-04T12:00:00.000Z',
};

const incompletePortrait: StudentQualityPortraitResponse = {
  ...completePortrait,
  metrics: completePortrait.metrics.map((metric) => (
    metric.key === 'review_base'
      ? { ...metric, score: null, source_record_id: null, source_created_at: null, detail_url: null }
      : metric
  )),
  overall_score: null,
  completeness: { complete: false, missing_metric_keys: ['review_base'], missing_metric_labels: ['评阅基础分'] },
};

function renderPage() {
  return render(<StudentQualityPortraitPage />);
}

describe('FEAT-STUDENT-QUALITY-PORTRAIT UI portrait contract', () => {
  beforeEach(() => {
    vi.mocked(fetchStudentQualityPortrait).mockReset();
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:UI:ROUTE:001 mounts both portrait routes through the existing App route tree without fetching fake records', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/student-quality-portrait']}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole('banner')).toHaveTextContent('单学生本地质量画像');
    expect(screen.getByText('请输入学生 ID 后查看该学生最新完成记录画像')).toBeInTheDocument();
    expect(fetchStudentQualityPortrait).not.toHaveBeenCalled();
    unmount();

    render(
      <MemoryRouter initialEntries={['/student-quality-portrait/student01']}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole('banner')).toHaveTextContent('单学生本地质量画像');
    expect(screen.getByLabelText('学生画像 ID')).toHaveValue('student01');
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:UI:QUERY:001 calls fetchStudentQualityPortrait with the entered student id and renders source timestamps and detail links', async () => {
    vi.mocked(fetchStudentQualityPortrait).mockResolvedValueOnce(completePortrait);
    const user = userEvent.setup();

    renderPage();
    await user.type(screen.getByLabelText('学生画像 ID'), 'student01');
    await user.click(screen.getByRole('button', { name: '查询' }));

    await waitFor(() => expect(fetchStudentQualityPortrait).toHaveBeenCalledWith('student01'));
    expect(screen.getByText('张三')).toBeInTheDocument();
    expect(screen.getByText('单学生本地质量画像研究')).toBeInTheDocument();

    for (const metric of completePortrait.metrics) {
      const metricCard = screen.getByText(metric.label).closest('article');
      expect(metricCard).not.toBeNull();
      expect(within(metricCard as HTMLElement).getByText(`${metric.score?.toFixed(1)}`)).toBeInTheDocument();
      expect(within(metricCard as HTMLElement).getByText(metric.source_created_at as string)).toBeInTheDocument();
      expect(within(metricCard as HTMLElement).getByRole('link', { name: '查看详情' })).toHaveAttribute('href', metric.detail_url);
    }
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:UI:SCENARIO:001 displays four metric sources and 80.0 分 comprehensive score when all scores are present', async () => {
    vi.mocked(fetchStudentQualityPortrait).mockResolvedValueOnce(completePortrait);
    const user = userEvent.setup();

    renderPage();
    await user.type(screen.getByLabelText('学生画像 ID'), 'student01');
    await user.click(screen.getByRole('button', { name: '查询' }));

    await screen.findByText('单学生论文全景质量画像');
    expect(screen.getByText('综合分').closest('article')).toHaveTextContent('80.0 分');
    expect(screen.queryByText('数据不完整')).not.toBeInTheDocument();
    expect(screen.getByText('四指标雷达图')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: '查看详情' })).toHaveLength(4);
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:UI:INCOMPLETE:001 displays 数据不完整 and the missing metric labels without converting null to zero', async () => {
    vi.mocked(fetchStudentQualityPortrait).mockResolvedValueOnce(incompletePortrait);
    const user = userEvent.setup();

    renderPage();
    await user.type(screen.getByLabelText('学生画像 ID'), 'student01');
    await user.click(screen.getByRole('button', { name: '查询' }));

    await screen.findByText('数据不完整');
    expect(screen.getByText('缺失项：评阅基础分')).toBeInTheDocument();

    const reviewMetricCard = screen.getByText('评阅基础分').closest('article');
    expect(reviewMetricCard).not.toBeNull();
    expect(within(reviewMetricCard as HTMLElement).getByText('缺失')).toBeInTheDocument();
    expect(within(reviewMetricCard as HTMLElement).getByText('暂无完成记录')).toBeInTheDocument();
    expect(within(reviewMetricCard as HTMLElement).queryByText('0.0')).not.toBeInTheDocument();
  });
});
