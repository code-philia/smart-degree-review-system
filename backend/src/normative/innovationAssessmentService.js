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

function normalizeRequiredText(payload, field, label, errors) {
  const value = typeof payload?.[field] === 'string' ? payload[field].trim() : '';
  if (!value) {
    errors.push({ field, message: `${label}不能为空` });
  }
  return value;
}

function normalizeAssessmentPayload(payload) {
  const errors = [];
  const normalizedInput = {
    thesis_title: normalizeRequiredText(payload, 'thesis_title', '论文题目', errors),
    degree_type: typeof payload?.degree_type === 'string' ? payload.degree_type.trim() : '',
    primary_discipline: normalizeRequiredText(payload, 'primary_discipline', '一级学科', errors),
    secondary_discipline: normalizeRequiredText(payload, 'secondary_discipline', '二级学科', errors),
    research_direction: normalizeRequiredText(payload, 'research_direction', '研究方向', errors),
    dimensions: {},
  };

  if (!['doctoral', 'master'].includes(normalizedInput.degree_type)) {
    errors.push({ field: 'degree_type', message: '学历层次必须为 doctoral 或 master' });
  }

  if (!payload?.dimensions || typeof payload.dimensions !== 'object') {
    errors.push({ field: 'dimensions', message: '五个创新性评估维度不能为空' });
  }

  for (const dimension of INNOVATION_ASSESSMENT_DIMENSIONS) {
    const dimensionPayload = payload?.dimensions?.[dimension.key];
    if (!dimensionPayload || typeof dimensionPayload !== 'object') {
      errors.push({ field: `dimensions.${dimension.key}`, message: `${dimension.label}维度不能为空` });
      continue;
    }

    const level = Number(dimensionPayload.level);
    if (!Number.isInteger(level) || level < 1 || level > 5) {
      errors.push({ field: `dimensions.${dimension.key}.level`, message: `${dimension.label}等级必须为 1-5 的整数` });
    }

    const evidence = typeof dimensionPayload.evidence === 'string' ? dimensionPayload.evidence.trim() : '';
    if (evidence.length < MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH) {
      errors.push({
        field: `dimensions.${dimension.key}.evidence`,
        message: `${dimension.label}证据不完整，需不少于 ${MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH} 个字符`,
      });
    }

    const improvementPlan = typeof dimensionPayload.improvement_plan === 'string'
      ? dimensionPayload.improvement_plan.trim()
      : '';
    if (improvementPlan.length < MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH) {
      errors.push({
        field: `dimensions.${dimension.key}.improvement_plan`,
        message: `${dimension.label}改进计划不完整，需不少于 ${MIN_INNOVATION_ASSESSMENT_TEXT_LENGTH} 个字符`,
      });
    }

    normalizedInput.dimensions[dimension.key] = {
      level,
      evidence,
      improvement_plan: improvementPlan,
    };
  }

  if (errors.length > 0) {
    throw createAssessmentError(400, '创新性量表评估输入不完整', errors);
  }

  return normalizedInput;
}

async function createInnovationAssessment(user, payload) {
  if (!user) {
    throw createAssessmentError(401, '请先登录后发起创新性量表评估');
  }
  if (!ALLOWED_INNOVATION_SCORING_ROLES.includes(user.role)) {
    throw createAssessmentError(403, '当前角色无权发起创新性量表评估');
  }

  const normalizedInput = normalizeAssessmentPayload(payload || {});
  const levels = Object.fromEntries(
    INNOVATION_ASSESSMENT_DIMENSIONS.map((dimension) => [
      dimension.key,
      normalizedInput.dimensions[dimension.key].level,
    ]),
  );
  const scoringSnapshot = await calculateInnovationScore(user, {
    degree_type: normalizedInput.degree_type,
    levels,
  });
  const snapshot = buildInnovationAssessmentSnapshot(user, normalizedInput, scoringSnapshot);
  const insertResult = await insertInnovationAssessmentSnapshot(snapshot);

  return {
    id: insertResult.id || snapshot.id,
    user_id: snapshot.user_id,
    thesis_title: snapshot.thesis_title,
    degree_type: snapshot.degree_type,
    primary_discipline: snapshot.primary_discipline,
    secondary_discipline: snapshot.secondary_discipline,
    research_direction: snapshot.research_direction,
    input_snapshot: snapshot.input_snapshot,
    scoring_snapshot: snapshot.scoring_snapshot,
    total_score: scoringSnapshot.total_score,
    grade_label: scoringSnapshot.grade_label,
    formula: scoringSnapshot.formula,
    dimensions: scoringSnapshot.dimensions,
    input: scoringSnapshot.input,
    disclaimer: snapshot.disclaimer,
    created_at: snapshot.created_at,
  };
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
