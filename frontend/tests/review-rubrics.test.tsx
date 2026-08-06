import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import apiClient from '../src/api';
import { fetchReviewRubrics } from '../src/api/normativeRules';
import ReviewRubricSelector from '../src/components/ReviewRubricSelector';

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return { ...actual, fetchReviewRubrics: vi.fn() };
});

const reviewRubricsResponse = {
  templates: [
    {
      template_id: 'academic_phd_natural_science',
      name: '学术型博士自然科学',
      required_sections: ['摘要', '引言', '研究方法', '结论', '参考文献'],
      minimum_reference_count: 80,
    },
    {
      template_id: 'academic_phd_humanities_social_science',
      name: '学术型博士人文社科',
      required_sections: ['摘要', '文献综述', '研究方法', '结论', '参考文献'],
      minimum_reference_count: 100,
    },
    {
      template_id: 'professional_phd',
      name: '专业型博士',
      required_sections: ['摘要', '实践问题', '研究方法', '结论', '参考文献'],
      minimum_reference_count: 60,
    },
    {
      template_id: 'academic_master',
      name: '学术型硕士',
      required_sections: ['摘要', '研究方法', '分析与讨论', '结论', '参考文献'],
      minimum_reference_count: 50,
    },
    {
      template_id: 'professional_master',
      name: '专业型硕士',
      required_sections: ['摘要', '实践背景', '方法与方案', '结论', '参考文献'],
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

describe('FEAT-AI-REVIEW-RUBRICS selector contract', () => {
  beforeEach(() => vi.mocked(fetchReviewRubrics).mockReset());

  it('loads and renders the standalone rubric selector independently from the PDF review route', async () => {
    vi.mocked(fetchReviewRubrics).mockResolvedValue(reviewRubricsResponse);
    render(<ReviewRubricSelector isOpen />);

    expect(await screen.findByText('正在加载评阅模板…')).toBeInTheDocument();
    await waitFor(() => expect(fetchReviewRubrics).toHaveBeenCalledTimes(1));
    const firstTemplate = await screen.findByText('学术型博士自然科学');
    const article = firstTemplate.closest('article');
    expect(article).toBeTruthy();
    expect(within(article as HTMLElement).getByText('最低参考文献数量：80')).toBeInTheDocument();
    expect(screen.getByText('共享客观计分项')).toBeInTheDocument();
    expect(screen.getByText(/客观分不低于 80/)).toBeInTheDocument();
  });

  it('uses the shared interceptor-enabled Axios client', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
