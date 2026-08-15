import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  createInnovationAssessment,
  type InnovationAssessmentRequest,
  type InnovationAssessmentResponse,
} from '../src/api/normativeRules';

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
    createInnovationAssessment: vi.fn(),
  };
});

const reqId = 'FEAT-INNOVATION-ANALYZE';
void reqId;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

function longText(label: string) {
  return `${label}证据围绕论文创新性评估展开，包含可核验资料和论证依据，超过二十个字符。`;
}

const scenarioPayload: InnovationAssessmentRequest = {
  thesis_title: '高校数字治理创新机制研究',
  degree_type: 'master',
  primary_discipline: '管理学',
  secondary_discipline: '公共管理',
  research_direction: '高校数字治理',
  dimensions: {
    research_topic: {
      level: 5,
      evidence: longText('研究选题'),
      improvement_plan: '研究选题改进计划将补充前沿文献和政策场景，增强问题意识。',
    },
    research_method: {
      level: 4,
      evidence: longText('研究方法'),
      improvement_plan: '研究方法改进计划将增加访谈样本和三角验证，提升方法可靠性。',
    },
    research_content: {
      level: 4,
      evidence: longText('研究内容'),
      improvement_plan: '研究内容改进计划将扩展案例比较和数据解释，增强论证深度。',
    },
    research_conclusion: {
      level: 3,
      evidence: longText('研究结论'),
      improvement_plan: '研究结论改进计划将明确适用边界和进一步研究方向，减少泛化。',
    },
    application_value: {
      level: 4,
      evidence: longText('应用价值'),
      improvement_plan: '应用价值改进计划将设计落地指标和推广条件，提升实践可用性。',
    },
  },
};

const scenarioResponse: InnovationAssessmentResponse = {
  id: 'assessment-001',
  user_id: 'student01',
  thesis_title: scenarioPayload.thesis_title,
  degree_type: 'master',
  primary_discipline: scenarioPayload.primary_discipline,
  secondary_discipline: scenarioPayload.secondary_discipline,
  research_direction: scenarioPayload.research_direction,
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
  input_snapshot: scenarioPayload,
  scoring_snapshot: {
    degree_type: 'master',
    total_score: 80,
    grade_label: '良好',
    formula: '维度原始分=等级×20；综合分=各维度原始分×权重之和。',
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
  },
  disclaimer: '本结果为量表自评，不代替专家评审或文献查新',
  created_at: '2026-08-05T10:00:00.000Z',
};

function renderRoute(initialPath = '/innovation-assessment') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

async function fillScenarioForm(user: ReturnType<typeof userEvent.setup>, payload = scenarioPayload) {
  await user.type(screen.getByLabelText('论文题目'), payload.thesis_title);
  await user.selectOptions(screen.getByLabelText('学历层次'), payload.degree_type);
  await user.type(screen.getByLabelText('一级学科'), payload.primary_discipline);
  await user.type(screen.getByLabelText('二级学科'), payload.secondary_discipline);
  await user.type(screen.getByLabelText('研究方向'), payload.research_direction);

  await user.selectOptions(screen.getByLabelText('研究选题等级'), String(payload.dimensions.research_topic.level));
  await user.type(screen.getByLabelText('研究选题证据'), payload.dimensions.research_topic.evidence);
  await user.type(screen.getByLabelText('研究选题改进计划'), payload.dimensions.research_topic.improvement_plan);

  await user.selectOptions(screen.getByLabelText('研究方法等级'), String(payload.dimensions.research_method.level));
  await user.type(screen.getByLabelText('研究方法证据'), payload.dimensions.research_method.evidence);
  await user.type(screen.getByLabelText('研究方法改进计划'), payload.dimensions.research_method.improvement_plan);

  await user.selectOptions(screen.getByLabelText('研究内容等级'), String(payload.dimensions.research_content.level));
  await user.type(screen.getByLabelText('研究内容证据'), payload.dimensions.research_content.evidence);
  await user.type(screen.getByLabelText('研究内容改进计划'), payload.dimensions.research_content.improvement_plan);

  await user.selectOptions(screen.getByLabelText('研究结论等级'), String(payload.dimensions.research_conclusion.level));
  await user.type(screen.getByLabelText('研究结论证据'), payload.dimensions.research_conclusion.evidence);
  await user.type(screen.getByLabelText('研究结论改进计划'), payload.dimensions.research_conclusion.improvement_plan);

  await user.selectOptions(screen.getByLabelText('应用价值等级'), String(payload.dimensions.application_value.level));
  await user.type(screen.getByLabelText('应用价值证据'), payload.dimensions.application_value.evidence);
  await user.type(screen.getByLabelText('应用价值改进计划'), payload.dimensions.application_value.improvement_plan);
}

describe('FEAT-INNOVATION-ANALYZE frontend route, form, and persisted-result contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(createInnovationAssessment).mockReset();
  });

  it('FEAT-INNOVATION-ANALYZE:FRONTEND:SCENARIO:001 submits all five dimensions and shows result only after a persisted response', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(createInnovationAssessment).mockResolvedValue(scenarioResponse);
    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByRole('heading', { name: '创新性量表评估' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '历史记录' })).toHaveAttribute('href', '/innovation-history');
    expect(screen.getByText(/当前登录用户：student01（STUDENT）/)).toBeInTheDocument();
    expect(screen.getByText('本结果为量表自评，不代替专家评审或文献查新')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '分析结果' })).not.toBeInTheDocument();

    await fillScenarioForm(user);
    await user.click(screen.getByRole('button', { name: 'AI 创新性分析' }));

    await waitFor(() => expect(createInnovationAssessment).toHaveBeenCalledWith(scenarioPayload));
    expect(await screen.findByRole('heading', { name: '分析结果' })).toBeInTheDocument();
    expect(screen.getByText('80 分')).toBeInTheDocument();
    expect(screen.getByText('良好')).toBeInTheDocument();
    expect(screen.getByText(scenarioPayload.thesis_title)).toBeInTheDocument();
    expect(screen.getByText(/保存编号：assessment-001/)).toBeInTheDocument();

    const progress = screen.getByRole('progressbar', { name: '创新性量表评估进度' });
    expect(progress).toHaveAttribute('aria-valuenow', '100');

    const detailTable = screen.getByRole('table', { name: '创新性量表分项分' });
    const researchMethodRow = within(detailTable).getByText('研究方法').closest('tr');
    expect(researchMethodRow).toBeTruthy();
    expect(within(researchMethodRow as HTMLTableRowElement).getByText('20%')).toBeInTheDocument();
    expect(within(researchMethodRow as HTMLTableRowElement).getByText('16')).toBeInTheDocument();
  });

  it('FEAT-INNOVATION-ANALYZE:FRONTEND:SCENARIO:002 displays server research-method evidence error and keeps the result panel hidden', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(createInnovationAssessment).mockRejectedValue({
      response: {
        status: 400,
        data: {
          code: 400,
          message: '评估输入不完整',
          errors: [
            {
              field: 'dimensions.research_method.evidence',
              message: '研究方法证据不完整，至少填写 20 个字符',
            },
          ],
        },
      },
    });
    const user = userEvent.setup();

    renderRoute();

    await fillScenarioForm(user, {
      ...scenarioPayload,
      dimensions: {
        ...scenarioPayload.dimensions,
        research_method: {
          ...scenarioPayload.dimensions.research_method,
          evidence: '证据不足',
        },
      },
    });
    await user.click(screen.getByRole('button', { name: 'AI 创新性分析' }));

    expect(await screen.findByText('研究方法证据不完整，至少填写 20 个字符')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '分析结果' })).not.toBeInTheDocument();
  });

  it('FEAT-INNOVATION-ANALYZE:FRONTEND:AUTHZ:001 renders a login prompt for anonymous users and does not submit local-only state', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: '发起创新性量表评估' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后提交量表自评/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(screen.queryByRole('button', { name: 'AI 创新性分析' })).not.toBeInTheDocument();
    expect(createInnovationAssessment).not.toHaveBeenCalled();
  });
});
