const { ALLOWED_INNOVATION_REPORT_ROLES } = require('./innovationReportService');
const { listInnovationAssessmentHistoryForUser } = require('./innovationAssessmentRepository');

const ALLOWED_INNOVATION_HISTORY_ROLES = ALLOWED_INNOVATION_REPORT_ROLES;

async function listInnovationHistoryForUser(user) {
  if (!user) {
    const error = new Error('请先登录后查看创新性评估历史');
    error.status = 401;
    throw error;
  }
  if (!ALLOWED_INNOVATION_HISTORY_ROLES.includes(user.role)) {
    const error = new Error('当前角色无权查看创新性评估历史');
    error.status = 403;
    throw error;
  }

  return listInnovationAssessmentHistoryForUser(user);
}

module.exports = {
  ALLOWED_INNOVATION_HISTORY_ROLES,
  listInnovationHistoryForUser,
};
