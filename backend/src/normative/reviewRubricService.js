const REVIEW_RUBRIC_ALLOWED_ROLES = Object.freeze(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

const SHARED_OBJECTIVE_SCORE_ITEMS = Object.freeze([
  { key: 'section_completeness', label: '章节完整性', points: 30 },
  { key: 'reference_count_and_numbering', label: '参考文献数量与编号', points: 20 },
  { key: 'methodology_section', label: '研究方法章节', points: 20 },
  { key: 'conclusion_section', label: '结论章节', points: 20 },
  { key: 'normative_detection_result', label: '规范检测结果', points: 10 },
]);

const REVIEW_RUBRIC_TEMPLATES = Object.freeze([
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
]);

function listReviewRubrics() {
  return {
    templates: REVIEW_RUBRIC_TEMPLATES.map((template) => ({
      ...template,
      required_sections: [...template.required_sections],
    })),
    shared_score_items: SHARED_OBJECTIVE_SCORE_ITEMS.map((item) => ({ ...item })),
    passing_rule: {
      minimum_objective_score: 80,
      no_required_section_missing: true,
      pass_label: '基础检查通过',
      revise_label: '需修改',
    },
  };
}

module.exports = {
  REVIEW_RUBRIC_ALLOWED_ROLES,
  REVIEW_RUBRIC_TEMPLATES,
  SHARED_OBJECTIVE_SCORE_ITEMS,
  listReviewRubrics,
};
