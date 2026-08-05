import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { fetchReviewRubrics } from '../src/api/normativeRules';
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
    fetchReviewRubrics: vi.fn(),
  };
});

const REQ_ID = 'FEAT-AI-REVIEW-RUBRICS';
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
    { template_id: 'academic_phd_natural_science', name: '学术型博士自然科学', required_sections: ['摘要', '引言', '研究方法', '结论', '参考文献'], minimum_reference_count: 80 },
    { template_id: 'academic_phd_humanities_social_science', name: '学术型博士人文社科', required_sections: ['摘要', '文献综述', '研究方法', '结论', '参考文献'], minimum_reference_count: 100 },
    { template_id: 'professional_phd', name: '专业型博士', required_sections: ['摘要', '实践问题', '研究方法', '结论', '参考文献'], minimum_reference_count: 60 },
    { template_id: 'academic_master', name: '学术型硕士', required_sections: ['摘要', '研究方法', '分析与讨论', '结论', '参考文献'], minimum_reference_count: 50 },
    { template_id: 'professional_master', name: '专业型硕士', required_sections: ['摘要', '实践背景', '方法与方案', '结论', '参考文献'], minimum_reference_count: 30 },
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

function renderRoute(initialPath = '/normative-check') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-AI-REVIEW-RUBRICS frontend rubric selector contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchReviewRubrics).mockReset();
  });

  it('opens the selector from the auxiliary review page and loads rubric data from the shared API client', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewRubrics).mockResolvedValue(reviewRubricsResponse);
    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByRole('heading', { name: '文档上传' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '打开模板选择器' }));

    expect(await screen.findByText('正在加载评阅模板…')).toBeInTheDocument();
    await waitFor(() => expect(fetchReviewRubrics).toHaveBeenCalledTimes(1));
    expect(fetchReviewRubrics).toHaveBeenCalledWith();

    expect(await screen.findByText('学术型博士自然科学')).toBeInTheDocument();
    expect(screen.getByText('学术型博士人文社科')).toBeInTheDocument();
    expect(screen.getByText('专业型博士')).toBeInTheDocument();
    expect(screen.getByText('学术型硕士')).toBeInTheDocument();
    expect(screen.getByText('专业型硕士')).toBeInTheDocument();

    const firstTemplate = screen.getByText('学术型博士自然科学').closest('article');
    expect(firstTemplate).toBeTruthy();
    expect(within(firstTemplate as HTMLElement).getByText('最低参考文献数量：80')).toBeInTheDocument();
    expect(within(firstTemplate as HTMLElement).getByText('必需章节')).toBeInTheDocument();
    expect(within(firstTemplate as HTMLElement).getByText('研究方法')).toBeInTheDocument();

    expect(screen.getByText('共享客观计分项')).toBeInTheDocument();
    expect(screen.getByText('章节完整性')).toBeInTheDocument();
    expect(screen.getByText('30 分')).toBeInTheDocument();
    expect(screen.getByText('基础检查通过')).toBeInTheDocument();
    expect(screen.getByText('需修改')).toBeInTheDocument();
    expect(screen.getByText(/客观分不低于 80 且无必需章节缺失时为“基础检查通过”/)).toBeInTheDocument();
  });

  it('shows the selector loading state and then an explicit error without fallback rubrics when the API fails', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewRubrics).mockRejectedValue(new Error('评阅模板加载失败'));
    const user = userEvent.setup();

    renderRoute();

    await user.click(await screen.findByRole('button', { name: '打开模板选择器' }));
    expect(await screen.findByText('正在加载评阅模板…')).toBeInTheDocument();
    expect(await screen.findByText('评阅模板加载失败')).toBeInTheDocument();
    expect(screen.queryByText('学术型博士自然科学')).not.toBeInTheDocument();
    expect(screen.queryByText('共享客观计分项')).not.toBeInTheDocument();
  });

  it('uses the shared interceptor-enabled Axios client for rubric requests', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
