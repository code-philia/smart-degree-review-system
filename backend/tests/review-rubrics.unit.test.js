import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const {
  REVIEW_RUBRIC_ALLOWED_ROLES,
  REVIEW_RUBRIC_TEMPLATES,
  SHARED_OBJECTIVE_SCORE_ITEMS,
  listReviewRubrics,
} = require('../src/normative/reviewRubricService');

const REQ_ID = 'FEAT-AI-REVIEW-RUBRICS';
void REQ_ID;

describe('FEAT-AI-REVIEW-RUBRICS service rubric catalog contract', () => {
  it('defines exactly the five built-in template categories with required sections and minimum references', () => {
    const rubrics = listReviewRubrics();

    expect(rubrics.templates.map((template) => template.name)).toEqual([
      '学术型博士自然科学',
      '学术型博士人文社科',
      '专业型博士',
      '学术型硕士',
      '专业型硕士',
    ]);
    expect(rubrics.templates).toHaveLength(5);

    for (const template of rubrics.templates) {
      expect(template.template_id).toEqual(expect.any(String));
      expect(template.required_sections.length).toBeGreaterThan(0);
      expect(template.required_sections).toEqual(expect.arrayContaining(['结论', '参考文献']));
      expect(template.minimum_reference_count).toEqual(expect.any(Number));
      expect(template.minimum_reference_count).toBeGreaterThan(0);
    }
  });

  it('returns shared objective score items totaling 100 with the required point allocation', () => {
    const rubrics = listReviewRubrics();

    expect(rubrics.shared_score_items).toEqual([
      { key: 'section_completeness', label: '章节完整性', points: 30 },
      { key: 'reference_count_and_numbering', label: '参考文献数量与编号', points: 20 },
      { key: 'methodology_section', label: '研究方法章节', points: 20 },
      { key: 'conclusion_section', label: '结论章节', points: 20 },
      { key: 'normative_detection_result', label: '规范检测结果', points: 10 },
    ]);
    expect(rubrics.shared_score_items.reduce((total, item) => total + item.points, 0)).toBe(100);
  });

  it('states the pass and revise rule required for objective review results', () => {
    expect(listReviewRubrics().passing_rule).toEqual({
      minimum_objective_score: 80,
      no_required_section_missing: true,
      pass_label: '基础检查通过',
      revise_label: '需修改',
    });
  });

  it('exposes immutable source constants and a fresh serializable response per call', () => {
    const first = listReviewRubrics();
    first.templates[0].required_sections.push('测试污染');
    first.shared_score_items[0].points = 0;

    const second = listReviewRubrics();
    expect(second.templates[0].required_sections).not.toContain('测试污染');
    expect(second.shared_score_items[0].points).toBe(30);
    expect(Object.isFrozen(REVIEW_RUBRIC_TEMPLATES)).toBe(true);
    expect(Object.isFrozen(SHARED_OBJECTIVE_SCORE_ITEMS)).toBe(true);
    expect(Object.isFrozen(REVIEW_RUBRIC_ALLOWED_ROLES)).toBe(true);
  });
});
