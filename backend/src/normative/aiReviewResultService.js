const { ALLOWED_AI_REVIEW_RUN_ROLES } = require('./aiReviewRunService');
const aiReviewRunRepository = require('./aiReviewRunRepository');

const ALLOWED_AI_REVIEW_RESULT_ROLES = ALLOWED_AI_REVIEW_RUN_ROLES;
const SUBJECTIVE_CONFIRMATION_ITEMS = Object.freeze([
  { key: 'academic_innovation', label: '学术创新性', status: '待人工确认' },
  { key: 'argument_depth', label: '论证深度与学术贡献', status: '待人工确认' },
  { key: 'discipline_fit', label: '学科适配性与专业判断', status: '待人工确认' },
]);

function createAiReviewResultError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function assertAiReviewResultAccess(user) {
  if (!user) {
    throw createAiReviewResultError(401, '请先登录后查看辅助评阅结果');
  }
  if (!ALLOWED_AI_REVIEW_RESULT_ROLES.includes(user.role)) {
    throw createAiReviewResultError(403, '当前角色无权查看辅助评阅结果');
  }
}

function decorateAiReviewResult(reviewRun) {
  if (!reviewRun) {
    return null;
  }

  return {
    ...reviewRun,
    objective_score_total: Array.isArray(reviewRun.score_items)
      ? reviewRun.score_items.reduce((sum, item) => sum + Number(item.score || 0), 0)
      : 0,
    subjective_confirmation_items: SUBJECTIVE_CONFIRMATION_ITEMS,
  };
}

async function getAiReviewResultForUser(user, reviewRunId) {
  assertAiReviewResultAccess(user);
  const result = await aiReviewRunRepository.findAiReviewRunForUser(reviewRunId, user.id);
  if (!result) {
    throw createAiReviewResultError(404, '辅助评阅结果不存在或无权查看');
  }
  return decorateAiReviewResult(result);
}

function buildAiReviewResultDownloadPayload(result) {
  return {
    report_type: 'ai_review_result',
    generated_at: new Date().toISOString(),
    result,
  };
}

module.exports = {
  ALLOWED_AI_REVIEW_RESULT_ROLES,
  SUBJECTIVE_CONFIRMATION_ITEMS,
  buildAiReviewResultDownloadPayload,
  getAiReviewResultForUser,
};
