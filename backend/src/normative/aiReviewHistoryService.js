const { ALLOWED_AI_REVIEW_RESULT_ROLES } = require('./aiReviewResultService');
const aiReviewRunRepository = require('./aiReviewRunRepository');

const ALLOWED_AI_REVIEW_HISTORY_ROLES = ALLOWED_AI_REVIEW_RESULT_ROLES;

function createAiReviewHistoryError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function assertAiReviewHistoryAccess(user) {
  if (!user) {
    throw createAiReviewHistoryError(401, '请先登录后查看辅助评阅历史');
  }
  if (!ALLOWED_AI_REVIEW_HISTORY_ROLES.includes(user.role)) {
    throw createAiReviewHistoryError(403, '当前角色无权查看辅助评阅历史');
  }
}

function toAiReviewHistoryRecord(reviewRun) {
  return {
    id: reviewRun.id,
    user_id: reviewRun.user_id,
    thesis_title: reviewRun.thesis_title,
    template_id: reviewRun.template_id,
    total_score: reviewRun.total_score,
    result_label: reviewRun.result_label,
    created_at: reviewRun.created_at,
  };
}

async function listAiReviewHistoryForUser(user) {
  assertAiReviewHistoryAccess(user);
  const runs = await aiReviewRunRepository.listAiReviewRunsForUser(user.id);
  return runs.map(toAiReviewHistoryRecord);
}

module.exports = {
  ALLOWED_AI_REVIEW_HISTORY_ROLES,
  listAiReviewHistoryForUser,
  toAiReviewHistoryRecord,
};
