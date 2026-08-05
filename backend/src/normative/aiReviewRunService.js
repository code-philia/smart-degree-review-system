const crypto = require('crypto');
const { analyzeDefaultNormativeRules } = require('./normativeService');
const {
  REVIEW_RUBRIC_ALLOWED_ROLES,
  REVIEW_RUBRIC_TEMPLATES,
  SHARED_OBJECTIVE_SCORE_ITEMS,
  listReviewRubrics,
} = require('./reviewRubricService');
const aiReviewRunRepository = require('./aiReviewRunRepository');

const ALLOWED_AI_REVIEW_RUN_ROLES = REVIEW_RUBRIC_ALLOWED_ROLES;
const MAX_AI_REVIEW_TEXT_BYTES = '5mb';
const ALLOWED_AI_REVIEW_FILE_EXTENSIONS = Object.freeze(['.txt', '.md']);

function createReviewRunError(status, message, errors) {
  const error = new Error(message);
  error.status = status;
  if (errors) {
    error.errors = errors;
  }
  return error;
}

function normalizeAiReviewRunPayload(payload = {}) {
  const errors = [];
  const thesisTitle = typeof payload.thesis_title === 'string' ? payload.thesis_title.trim() : '';
  const templateId = typeof payload.template_id === 'string' ? payload.template_id.trim() : '';
  const text = typeof payload.text === 'string' ? payload.text : '';
  const sourceType = payload.source_type === 'file' ? 'file' : 'paste';
  const sourceFilename = typeof payload.source_filename === 'string' && payload.source_filename.trim()
    ? payload.source_filename.trim()
    : null;

  if (!thesisTitle) {
    errors.push({ field: 'thesis_title', message: '论文题目不能为空' });
  }
  if (!templateId) {
    errors.push({ field: 'template_id', message: '评阅模板不能为空' });
  }
  if (!text.trim()) {
    errors.push({ field: 'text', message: '论文文本不能为空' });
  }
  if (sourceType === 'file' && !sourceFilename) {
    errors.push({ field: 'source_filename', message: '上传文件需要提供文件名' });
  }

  if (errors.length > 0) {
    throw createReviewRunError(400, '辅助评阅输入不完整', errors);
  }

  return { thesisTitle, templateId, text, sourceType, sourceFilename };
}

function findRubricTemplate(templateId) {
  return REVIEW_RUBRIC_TEMPLATES.find((template) => template.template_id === templateId) || null;
}

function identifySections(text, requiredSections) {
  return requiredSections.map((section) => ({
    name: section,
    present: text.split(/\r?\n/).some((line) => line.trim() === section || line.trim().startsWith(`${section}：`)),
  }));
}

function countReferences(text) {
  const referenceIndex = text.split(/\r?\n/).findIndex((line) => line.trim() === '参考文献');
  if (referenceIndex < 0) {
    return 0;
  }
  return text.split(/\r?\n/).slice(referenceIndex + 1).filter((line) => /^\s*\[\d+\]/.test(line)).length;
}

function buildScoreItems(template, sectionSnapshot, referenceCount, normativeIssues) {
  const missingSections = sectionSnapshot.filter((section) => !section.present).map((section) => section.name);
  return SHARED_OBJECTIVE_SCORE_ITEMS.map((item) => {
    if (item.key === 'section_completeness') {
      return { ...item, score: missingSections.length ? 0 : item.points, findings: missingSections };
    }
    if (item.key === 'reference_count_and_numbering') {
      return {
        ...item,
        score: referenceCount >= template.minimum_reference_count ? item.points : 0,
        findings: [`参考文献条目：${referenceCount}/${template.minimum_reference_count}`],
      };
    }
    if (item.key === 'methodology_section') {
      return { ...item, score: missingSections.includes('研究方法') ? 0 : item.points, findings: missingSections.includes('研究方法') ? ['缺少研究方法章节'] : [] };
    }
    if (item.key === 'conclusion_section') {
      return { ...item, score: missingSections.includes('结论') ? 0 : item.points, findings: missingSections.includes('结论') ? ['缺少结论章节'] : [] };
    }
    return { ...item, score: normativeIssues.length ? 0 : item.points, findings: normativeIssues.map((issue) => issue.message).slice(0, 5) };
  });
}

async function createAiReviewRun(user, payload = {}) {
  if (!user) {
    throw createReviewRunError(401, '请先登录后发起辅助评阅');
  }
  if (!ALLOWED_AI_REVIEW_RUN_ROLES.includes(user.role)) {
    throw createReviewRunError(403, '当前角色无权发起辅助评阅');
  }

  const normalized = normalizeAiReviewRunPayload(payload);
  const template = findRubricTemplate(normalized.templateId);
  if (!template) {
    throw createReviewRunError(400, '评阅模板不存在');
  }

  const sectionSnapshot = identifySections(normalized.text, template.required_sections);
  const missingSections = sectionSnapshot.filter((section) => !section.present).map((section) => section.name);
  const referenceCount = countReferences(normalized.text);
  const normativeAnalysis = await analyzeDefaultNormativeRules(normalized.text);
  const normativeIssues = Array.isArray(normativeAnalysis.issues) ? normativeAnalysis.issues : [];
  const scoreItems = buildScoreItems(template, sectionSnapshot, referenceCount, normativeIssues);
  const totalScore = scoreItems.reduce((sum, item) => sum + item.score, 0);
  const passingRule = listReviewRubrics().passing_rule;
  const resultLabel = totalScore >= passingRule.minimum_objective_score && missingSections.length === 0
    ? passingRule.pass_label
    : passingRule.revise_label;

  const reviewRun = {
    id: crypto.randomUUID(),
    user_id: user.id,
    thesis_title: normalized.thesisTitle,
    template_id: template.template_id,
    source_type: normalized.sourceType,
    source_filename: normalized.sourceFilename,
    original_text: normalized.text,
    section_snapshot: sectionSnapshot,
    reference_count: referenceCount,
    character_count: Array.from(normalized.text).length,
    normative_issues: normativeIssues,
    score_items: scoreItems,
    total_score: totalScore,
    result_label: resultLabel,
    missing_sections: missingSections,
    rubric_snapshot: {
      template,
      shared_score_items: SHARED_OBJECTIVE_SCORE_ITEMS,
      passing_rule: passingRule,
    },
    created_at: new Date().toISOString(),
  };

  return aiReviewRunRepository.insertAiReviewRun(reviewRun);
}

module.exports = {
  ALLOWED_AI_REVIEW_FILE_EXTENSIONS,
  ALLOWED_AI_REVIEW_RUN_ROLES,
  MAX_AI_REVIEW_TEXT_BYTES,
  createAiReviewRun,
};
