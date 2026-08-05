const crypto = require('crypto');
const {
  ALLOWED_INNOVATION_SCORING_ROLES,
  MAX_INNOVATION_SCORING_JSON_BYTES,
  calculateInnovationScore,
} = require('./innovationScoringService');
const { insertInnovationAssessmentSnapshot } = require('./innovationAssessmentRepository');

const MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH = 20;
const INNOVATION_ASSESSMENT_DIMENSIONS = [
  { key: 'research_topic', label: '研究选题' },
  { key: 'research_method', label: '研究方法' },
  { key: 'research_content', label: '研究内容' },
  { key: 'research_conclusion', label: '研究结论' },
  { key: 'application_value', label: '应用价值' },
];
const INNOVATION_ASSESSMENT_DISCLAIMER = '本结果为量表自评，不代替专家评审或文献查新';

function createAssessmentError(status, message, errors) {
  const error = new Error(message);
  error.status = status;
  if (errors) {
    error.errors = errors;
  }
  return error;
}

async function createInnovationAssessment(user, payload) {
  if (!user) {
    throw createAssessmentError(401, '请先登录后发起创新性量表评估');
  }
  if (!ALLOWED_INNOVATION_SCORING_ROLES.includes(user.role)) {
    throw createAssessmentError(403, '当前角色无权发起创新性量表评估');
  }

  throw createAssessmentError(501, '创新性量表评估快照保存尚未实现');
}

function buildInnovationAssessmentSnapshot(user, normalizedInput, scoringSnapshot) {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    user_id: user.id,
    thesis_title: normalizedInput.thesis_title,
    degree_type: normalizedInput.degree_type,
    primary_discipline: normalizedInput.primary_discipline,
    secondary_discipline: normalizedInput.secondary_discipline,
    research_direction: normalizedInput.research_direction,
    input_snapshot: normalizedInput,
    scoring_snapshot: scoringSnapshot,
    disclaimer: INNOVATION_ASSESSMENT_DISCLAIMER,
    created_at: now,
  };
}

module.exports = {
  ALLOWED_INNOVATION_ASSESSMENT_ROLES: ALLOWED_INNOVATION_SCORING_ROLES,
  INNOVATION_ASSESSMENT_DIMENSIONS,
  INNOVATION_ASSESSMENT_DISCLAIMER,
  MAX_INNOVATION_ASSESSMENT_JSON_BYTES: MAX_INNOVATION_SCORING_JSON_BYTES,
  MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH,
  buildInnovationAssessmentSnapshot,
  calculateInnovationScore,
  createInnovationAssessment,
  insertInnovationAssessmentSnapshot,
};
