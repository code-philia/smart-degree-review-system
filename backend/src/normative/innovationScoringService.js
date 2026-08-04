const ALLOWED_INNOVATION_SCORING_ROLES = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];
const MAX_INNOVATION_SCORING_JSON_BYTES = '32kb';

const INNOVATION_SCORE_DIMENSIONS = [
  { key: 'research_topic', label: '研究选题' },
  { key: 'research_method', label: '研究方法' },
  { key: 'research_content', label: '研究内容' },
  { key: 'research_conclusion', label: '研究结论' },
  { key: 'application_value', label: '应用价值' },
];

const INNOVATION_SCORE_WEIGHTS = {
  doctoral: {
    research_topic: 0.25,
    research_method: 0.25,
    research_content: 0.2,
    research_conclusion: 0.2,
    application_value: 0.1,
  },
  master: {
    research_topic: 0.2,
    research_method: 0.2,
    research_content: 0.25,
    research_conclusion: 0.2,
    application_value: 0.15,
  },
};

const FORMULA_BY_DEGREE_TYPE = {
  doctoral: '维度原始分=等级×20；综合分=各维度原始分×权重之和。博士权重依次为 25%、25%、20%、20%、10%。',
  master: '维度原始分=等级×20；综合分=各维度原始分×权重之和。硕士权重依次为 20%、20%、25%、20%、15%。',
};

function createServiceError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function assertAllowedUser(user) {
  if (!user) {
    throw createServiceError(401, '请先登录后计算创新性分数');
  }
  if (!ALLOWED_INNOVATION_SCORING_ROLES.includes(user.role)) {
    throw createServiceError(403, '当前角色无权计算创新性分数');
  }
}

function normalizePayload(payload) {
  if (!payload || typeof payload !== 'object') {
    throw createServiceError(400, '评分输入不能为空');
  }

  const degreeType = payload.degree_type;
  if (!Object.prototype.hasOwnProperty.call(INNOVATION_SCORE_WEIGHTS, degreeType)) {
    throw createServiceError(400, '学位类型必须为 doctoral 或 master');
  }

  if (!payload.levels || typeof payload.levels !== 'object') {
    throw createServiceError(400, '五个评分维度等级不能为空');
  }

  const levels = {};
  for (const dimension of INNOVATION_SCORE_DIMENSIONS) {
    const level = payload.levels[dimension.key];
    if (!Number.isInteger(level) || level < 1 || level > 5) {
      throw createServiceError(400, `${dimension.label}等级必须为 1-5 的整数`);
    }
    levels[dimension.key] = level;
  }

  return {
    degree_type: degreeType,
    levels,
  };
}

function classifyGrade(totalScore) {
  if (totalScore >= 90) {
    return '优秀';
  }
  if (totalScore >= 80) {
    return '良好';
  }
  if (totalScore >= 60) {
    return '一般';
  }
  return '待提升';
}

async function calculateInnovationScore(user, payload) {
  assertAllowedUser(user);
  const input = normalizePayload(payload);
  const weights = INNOVATION_SCORE_WEIGHTS[input.degree_type];

  const dimensions = INNOVATION_SCORE_DIMENSIONS.map((dimension) => {
    const level = input.levels[dimension.key];
    const rawScore = level * 20;
    const weight = weights[dimension.key];
    const weightedScore = Number((rawScore * weight).toFixed(2));

    return {
      key: dimension.key,
      label: dimension.label,
      level,
      raw_score: rawScore,
      weight,
      weighted_score: weightedScore,
    };
  });

  const totalScore = Number(dimensions.reduce((sum, dimension) => sum + dimension.weighted_score, 0).toFixed(2));

  return {
    degree_type: input.degree_type,
    total_score: totalScore,
    grade_label: classifyGrade(totalScore),
    formula: FORMULA_BY_DEGREE_TYPE[input.degree_type],
    dimensions,
    input,
  };
}

module.exports = {
  ALLOWED_INNOVATION_SCORING_ROLES,
  INNOVATION_SCORE_DIMENSIONS,
  INNOVATION_SCORE_WEIGHTS,
  MAX_INNOVATION_SCORING_JSON_BYTES,
  calculateInnovationScore,
};
