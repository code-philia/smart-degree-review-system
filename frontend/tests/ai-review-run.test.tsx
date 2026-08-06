import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { createAiReviewRun, fetchReviewRubrics } from '../src/api/normativeRules';

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
    fetchReviewRubrics: vi.fn(),
    createAiReviewRun: vi.fn(),
  };
});

const REQ_ID = 'FEAT-AI-REVIEW-RUN';
void REQ_ID;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const reviewRubricsResponse = {
  templates: [
    {
      template_id: 'academic_phd_natural_science',
      name: '学术型博士自然科学',
      required_sections: ['摘要', '关键词', '引言', '研究方法', '实验与结果', '结论', '参考文献'],
      minimum_reference_count: 80,
    },
    {
      template_id: 'academic_phd_humanities_social_science',
      name: '学术型博士人文社科',
      required_sections: ['摘要', '关键词', '引言', '文献综述', '研究方法', '主体论证', '结论', '参考文献'],
      minimum_reference_count: 100,
    },
    {
      template_id: 'professional_phd',
      name: '专业型博士',
      required_sections: ['摘要', '关键词', '引言', '实践问题', '研究方法', '应用方案', '结论', '参考文献'],
      minimum_reference_count: 60,
    },
    {
      template_id: 'academic_master',
      name: '学术型硕士',
      required_sections: ['摘要', '关键词', '引言', '研究方法', '分析与讨论', '结论', '参考文献'],
      minimum_reference_count: 50,
    },
    {
      template_id: 'professional_master',
      name: '专业型硕士',
      required_sections: ['摘要', '关键词', '引言', '实践背景', '方法与方案', '结论', '参考文献'],
      minimum_reference_count: 30,
    },
  ],
  shared_score_items: [
    { key: 'section_completeness', label: '章节完整性', points: 30 },
    { key: 'reference_count_and_numbering', label: '参考文献数量与编号', points: 20 },
    { key: 'methodology_section', label: '研究方法章节', points: 20 },
    { key: 'conclusion_section', label: '结论章节', points: 20 },
    { key: 'normative_detection_result', label: '规范检测结果', points: 10 },
  ],
  passing_rule: {
    minimum_objective_score: 80,
    no_required_section_missing: true,
    pass_label: '基础检查通过',
    revise_label: '需修改',
  },
};

function buildReferenceLines(count: number) {
  return Array.from({ length: count }, (_, index) => `[${index + 1}] 引用条目 ${index + 1}`).join('\n');
}

function buildMissingConclusionText(referenceCount = 50) {
  return ['摘要', '关键词', '引言', '研究方法', '分析与讨论', '参考文献', buildReferenceLines(referenceCount)].join(
    '\n',
  );
}

function renderRoute(initialPath = '/ai-review') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

function reviewTemplateCard(name: string) {
  return screen.getByRole('button', { name });
}

describe('FEAT-AI-REVIEW-RUN frontend route and workflow contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchReviewRubrics).mockReset();
    vi.mocked(createAiReviewRun).mockReset();
  });

  it('routes the home-page 发起评阅 link into the owned /ai-review workflow without leaving the shared app tree', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewRubrics).mockResolvedValue(reviewRubricsResponse);
    const user = userEvent.setup();

    renderRoute('/');

    expect(await screen.findByRole('heading', { name: '智慧学位 AI 评阅辅助系统' })).toBeInTheDocument();
    await user.click(screen.getByRole('link', { name: '发起评阅' }));

    expect(await screen.findByRole('heading', { name: 'AI 智能评阅' })).toBeInTheDocument();
    expect(await screen.findByText('智能评阅')).toBeInTheDocument();
    expect(vi.mocked(fetchReviewRubrics)).toHaveBeenCalledTimes(1);
  });

  it('shows the shared anonymous login prompt on /ai-review instead of fake review controls', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute('/ai-review');

    expect(await screen.findByRole('heading', { name: 'AI 智能评阅' })).toBeInTheDocument();
    expect(screen.getByText('请先登录后选择模板并发起辅助评阅，后台会在生成结果前执行角色授权。')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(screen.queryByRole('button', { name: '智能评阅' })).not.toBeInTheDocument();
  });

  it('renders backend-loaded rubric cards and returns a 需修改 result when the submitted text is missing 结论', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewRubrics).mockResolvedValue(reviewRubricsResponse);
    vi.mocked(createAiReviewRun).mockResolvedValue({
      id: 'review-run-001',
      user_id: 'student01',
      thesis_title: '高校数字治理平台评阅研究',
      template_id: 'academic_master',
      source_type: 'paste',
      source_filename: null,
      original_text: buildMissingConclusionText(),
      section_snapshot: [
        { name: '摘要', present: true },
        { name: '关键词', present: true },
        { name: '引言', present: true },
        { name: '研究方法', present: true },
        { name: '分析与讨论', present: true },
        { name: '结论', present: false },
        { name: '参考文献', present: true },
      ],
      reference_count: 50,
      character_count: Array.from(buildMissingConclusionText()).length,
      normative_issues: [
        {
          rule_id: 'NORM-001',
          category: '章节顺序',
          severity: 'high',
          line: 6,
          column: 1,
          excerpt: '结论',
          message: '缺少必需章节：结论',
          suggestion: '补充“结论”并按规定顺序排列',
        },
      ],
      score_items: [
        { key: 'section_completeness', label: '章节完整性', points: 30, score: 0, findings: ['结论'] },
        {
          key: 'reference_count_and_numbering',
          label: '参考文献数量与编号',
          points: 20,
          score: 20,
          findings: ['参考文献条目：50/50'],
        },
        { key: 'methodology_section', label: '研究方法章节', points: 20, score: 20, findings: [] },
        { key: 'conclusion_section', label: '结论章节', points: 20, score: 0, findings: ['缺少结论章节'] },
        {
          key: 'normative_detection_result',
          label: '规范检测结果',
          points: 10,
          score: 0,
          findings: ['缺少必需章节：结论'],
        },
      ],
      total_score: 40,
      result_label: '需修改',
      missing_sections: ['结论'],
      rubric_snapshot: reviewRubricsResponse,
      created_at: '2026-01-01T00:00:00.000Z',
    });
    const user = userEvent.setup();

    renderRoute('/ai-review');

    expect(await screen.findByRole('heading', { name: 'AI 智能评阅' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '选择评阅模板' })).toBeInTheDocument();
    expect(screen.getByText('学术型硕士')).toBeInTheDocument();
    expect(screen.getByText(/必需章节：摘要、关键词、引言、研究方法、分析与讨论、结论、参考文献/)).toBeInTheDocument();

    await user.click(reviewTemplateCard('学术型硕士'));
    fireEvent.change(screen.getByLabelText('论文题目'), { target: { value: '高校数字治理平台评阅研究' } });
    fireEvent.change(screen.getByLabelText('论文文本'), { target: { value: buildMissingConclusionText() } });
    await user.click(screen.getByRole('button', { name: '智能评阅' }));

    await waitFor(() =>
      expect(createAiReviewRun).toHaveBeenCalledWith({
        thesis_title: '高校数字治理平台评阅研究',
        template_id: 'academic_master',
        text: buildMissingConclusionText(),
        source_type: 'paste',
        source_filename: null,
      }),
    );
    expect(await screen.findByRole('heading', { name: '评阅结果' })).toBeInTheDocument();
    expect(screen.getByText('40 分 · 需修改')).toBeInTheDocument();
    expect(screen.getByText('缺失章节：结论')).toBeInTheDocument();
  });

  it('shows file validation errors for unsupported extensions and oversize .md uploads without submitting review data', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewRubrics).mockResolvedValue(reviewRubricsResponse);
    const user = userEvent.setup();
    const { container } = renderRoute('/ai-review');

    await screen.findByRole('heading', { name: 'AI 智能评阅' });
    const fileInput = container.querySelector('input[type="file"]');
    expect(fileInput).toBeInstanceOf(HTMLInputElement);

    await user.upload(fileInput as HTMLInputElement, new File(['PDF'], 'paper.pdf', { type: 'application/pdf' }));
    expect(await screen.findByText('仅支持上传 .txt 或 .md 文件')).toBeInTheDocument();
    expect(createAiReviewRun).not.toHaveBeenCalled();

    await user.upload(
      fileInput as HTMLInputElement,
      new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'oversize.md', { type: 'text/markdown' }),
    );
    expect(await screen.findByText('文件大小不能超过 5 MB')).toBeInTheDocument();
    expect(createAiReviewRun).not.toHaveBeenCalled();
  });

  it('renders the template-loading error explicitly when rubric fetch fails instead of fabricating fallback templates', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewRubrics).mockRejectedValue(new Error('评阅模板加载失败'));

    renderRoute('/ai-review');

    expect(await screen.findByRole('heading', { name: 'AI 智能评阅' })).toBeInTheDocument();
    expect(await screen.findByText('评阅模板加载失败')).toBeInTheDocument();
    expect(screen.queryByText('学术型博士自然科学')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '智能评阅' })).not.toBeInTheDocument();
  });
});
