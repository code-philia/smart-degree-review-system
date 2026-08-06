import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  downloadInnovationReportJson,
  fetchInnovationReport,
  type InnovationAssessmentResponse,
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
    fetchInnovationReport: vi.fn(),
  };
});

const REQ_ID = 'FEAT-INNOVATION-REPORT';
void REQ_ID;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const reportRecord: InnovationAssessmentResponse = {
  id: 'innovation-report-ui-001',
  user_id: 'student01',
  thesis_title: '高校数字治理创新机制研究',
  degree_type: 'master',
  primary_discipline: '管理学',
  secondary_discipline: '公共管理',
  research_direction: '高校数字治理',
  total_score: 80,
  grade_label: '良好',
  formula: '维度原始分=等级×20；综合分=各维度原始分×权重之和。硕士权重依次为 20%、20%、25%、20%、15%。',
  dimensions: [
    { key: 'research_topic', label: '研究选题', level: 5, raw_score: 100, weight: 0.2, weighted_score: 20 },
    { key: 'research_method', label: '研究方法', level: 4, raw_score: 80, weight: 0.2, weighted_score: 16 },
    { key: 'research_content', label: '研究内容', level: 4, raw_score: 80, weight: 0.25, weighted_score: 20 },
    { key: 'research_conclusion', label: '研究结论', level: 3, raw_score: 60, weight: 0.2, weighted_score: 12 },
    { key: 'application_value', label: '应用价值', level: 4, raw_score: 80, weight: 0.15, weighted_score: 12 },
  ],
  input: {
    degree_type: 'master',
    levels: {
      research_topic: 5,
      research_method: 4,
      research_content: 4,
      research_conclusion: 3,
      application_value: 4,
    },
  },
  input_snapshot: {
    thesis_title: '高校数字治理创新机制研究',
    degree_type: 'master',
    primary_discipline: '管理学',
    secondary_discipline: '公共管理',
    research_direction: '高校数字治理',
    dimensions: {
      research_topic: {
        level: 5,
        evidence: '研究选题证据围绕论文创新点、资料来源和可验证路径展开。',
        improvement_plan: '研究选题改进计划将补充前沿文献和政策场景。',
      },
      research_method: {
        level: 4,
        evidence: '研究方法证据围绕论文创新点、资料来源和可验证路径展开。',
        improvement_plan: '研究方法改进计划将增加访谈样本和三角验证。',
      },
      research_content: {
        level: 4,
        evidence: '研究内容证据围绕论文创新点、资料来源和可验证路径展开。',
        improvement_plan: '研究内容改进计划将扩展案例比较和数据解释。',
      },
      research_conclusion: {
        level: 3,
        evidence: '研究结论证据围绕论文创新点、资料来源和可验证路径展开。',
        improvement_plan: '研究结论改进计划将明确适用边界和进一步研究方向。',
      },
      application_value: {
        level: 4,
        evidence: '应用价值证据围绕论文创新点、资料来源和可验证路径展开。',
        improvement_plan: '应用价值改进计划将设计落地指标和推广条件。',
      },
    },
  },
  scoring_snapshot: {
    degree_type: 'master',
    total_score: 80,
    grade_label: '良好',
    formula: '维度原始分=等级×20；综合分=各维度原始分×权重之和。硕士权重依次为 20%、20%、25%、20%、15%。',
    dimensions: [],
    input: {
      degree_type: 'master',
      levels: {
        research_topic: 5,
        research_method: 4,
        research_content: 4,
        research_conclusion: 3,
        application_value: 4,
      },
    },
  },
  disclaimer: '本结果为量表自评，不代替专家评审或文献查新',
  created_at: '2026-08-05T10:00:00.000Z',
};
reportRecord.scoring_snapshot.dimensions = reportRecord.dimensions;

function renderRoute(initialPath = '/innovation-assessments/innovation-report-ui-001') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-INNOVATION-REPORT frontend page, route, and client contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchInnovationReport).mockReset();
    vi.mocked(downloadInnovationReportJson).mockReset();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:innovation-report');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLElement.prototype, 'click').mockImplementation(() => undefined);
    vi.spyOn(window, 'print').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('FEAT-INNOVATION-REPORT:UI:001 renders login-required state and does not fetch protected report data for anonymous users', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: '学位论文创新性分析报告' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后查看已完成的创新性量表报告/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(fetchInnovationReport).not.toHaveBeenCalled();
  });

  it('FEAT-INNOVATION-REPORT:UI:002 resolves the app route and renders runtime basic info, score, tabs, and local chart-ready values consistently', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchInnovationReport).mockResolvedValue(reportRecord);
    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByRole('heading', { name: '学位论文创新性分析报告' })).toBeInTheDocument();
    await waitFor(() => expect(fetchInnovationReport).toHaveBeenCalledWith('innovation-report-ui-001'));
    const tabNav = screen.getByRole('navigation', { name: '创新性报告章节' });
    expect(within(tabNav).getByRole('button', { name: '基本信息' })).toBeInTheDocument();
    expect(within(tabNav).getByRole('button', { name: '核心指标雷达图' })).toBeInTheDocument();
    expect(within(tabNav).getByRole('button', { name: '子指标热力图' })).toBeInTheDocument();
    expect(within(tabNav).getByRole('button', { name: '分项评价' })).toBeInTheDocument();
    expect(within(tabNav).getByRole('button', { name: '综合评价与建议' })).toBeInTheDocument();

    const basicInfo = await screen.findByTestId('innovation-report-basic-info');
    expect(basicInfo).toHaveTextContent(reportRecord.thesis_title);
    expect(basicInfo).toHaveTextContent('student01');
    expect(basicInfo).toHaveTextContent(reportRecord.primary_discipline);
    expect(basicInfo).toHaveTextContent(reportRecord.secondary_discipline);
    expect(basicInfo).toHaveTextContent(reportRecord.research_direction);
    expect(screen.getByTestId('innovation-report-grade')).toHaveTextContent(reportRecord.grade_label);
    expect(screen.getByTestId('innovation-report-total-score')).toHaveTextContent(String(reportRecord.total_score));

    await user.click(screen.getByRole('button', { name: '核心指标雷达图' }));
    expect(screen.getByRole('img', { name: '五维创新性雷达图' })).toBeInTheDocument();
    for (const dimension of reportRecord.dimensions) {
      const radarPoint = screen.getByTestId(`innovation-report-radar-dimension-${dimension.key}`);
      expect(radarPoint).toHaveAttribute('data-level', String(dimension.level));
      expect(radarPoint).toHaveAttribute('data-weighted-score', String(dimension.weighted_score));
    }

    await user.click(screen.getByRole('button', { name: '子指标热力图' }));
    const heatmap = screen.getByRole('table', { name: '五维评级热力矩阵' });
    expect(heatmap).toBeInTheDocument();
    expect(screen.getByTestId('innovation-report-heatmap-dimension-research_method')).toHaveAttribute(
      'data-weighted-score',
      '16',
    );

    await user.click(screen.getByRole('button', { name: '分项评价' }));
    const methodText = screen.getByTestId('innovation-report-dimension-text-research_method');
    expect(methodText).toHaveTextContent('研究方法');
    expect(methodText).toHaveTextContent('等级 4');
    expect(methodText).toHaveTextContent('权重 20%');
    expect(methodText).toHaveTextContent('加权分 16');
    expect(methodText).toHaveTextContent(reportRecord.input_snapshot.dimensions.research_method.evidence);
    expect(methodText).toHaveTextContent(reportRecord.input_snapshot.dimensions.research_method.improvement_plan);

    await user.click(screen.getByRole('button', { name: '综合评价与建议' }));
    expect(screen.getByTestId('innovation-report-formula')).toHaveTextContent(reportRecord.formula);
    expect(screen.getByTestId('innovation-report-summary-score')).toHaveTextContent(String(reportRecord.total_score));
    expect(screen.getByTestId('innovation-report-summary-grade')).toHaveTextContent(reportRecord.grade_label);
    expect(screen.getByTestId('innovation-report-disclaimer')).toHaveTextContent(reportRecord.disclaimer);
  });

  it('FEAT-INNOVATION-REPORT:UI:003 downloads JSON only from a loaded report and invokes browser print from the report page', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchInnovationReport).mockResolvedValue(reportRecord);
    vi.mocked(downloadInnovationReportJson).mockResolvedValue(
      new Blob([JSON.stringify(reportRecord)], { type: 'application/json;charset=utf-8' }),
    );
    const user = userEvent.setup();

    renderRoute();

    await screen.findByTestId('innovation-report-basic-info');
    await user.click(screen.getByRole('button', { name: /下载 JSON|下载 UTF-8 JSON/ }));
    await waitFor(() => expect(downloadInnovationReportJson).toHaveBeenCalledWith('innovation-report-ui-001'));
    expect(URL.createObjectURL).toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '浏览器打印' }));
    expect(window.print).toHaveBeenCalled();
  });

  it('FEAT-INNOVATION-REPORT:API-CLIENT:001 uses shared Axios same-origin report detail and JSON blob download paths', async () => {
    const getSpy = vi.spyOn(apiClient, 'get');
    getSpy.mockResolvedValueOnce({ data: reportRecord });
    getSpy.mockResolvedValueOnce({ data: new Blob(['{}'], { type: 'application/json' }) });

    const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
    await expect(actual.fetchInnovationReport('innovation-report-ui-001')).resolves.toEqual(reportRecord);
    await expect(actual.downloadInnovationReportJson('innovation-report-ui-001')).resolves.toBeInstanceOf(Blob);

    expect(getSpy).toHaveBeenNthCalledWith(1, '/normative/innovation-assessments/innovation-report-ui-001');
    expect(getSpy).toHaveBeenNthCalledWith(2, '/normative/innovation-assessments/innovation-report-ui-001/download', {
      responseType: 'blob',
      headers: { Accept: 'application/json' },
    });
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
