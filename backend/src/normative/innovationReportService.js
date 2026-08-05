const { ALLOWED_INNOVATION_ASSESSMENT_ROLES } = require('./innovationAssessmentService');
const {
  buildInnovationAssessmentDownloadPayload,
  getInnovationAssessmentReportForUser,
} = require('./innovationAssessmentRepository');

const ALLOWED_INNOVATION_REPORT_ROLES = ALLOWED_INNOVATION_ASSESSMENT_ROLES;

async function getInnovationReportForUser(user, reportId) {
  if (!user) {
    const error = new Error('请先登录后查看创新性量表报告');
    error.status = 401;
    throw error;
  }
  if (!ALLOWED_INNOVATION_REPORT_ROLES.includes(user.role)) {
    const error = new Error('当前角色无权查看创新性量表报告');
    error.status = 403;
    throw error;
  }

  return getInnovationAssessmentReportForUser(user, reportId);
}

function buildInnovationReportDownloadPayload(report) {
  return buildInnovationAssessmentDownloadPayload(report);
}

module.exports = {
  ALLOWED_INNOVATION_REPORT_ROLES,
  buildInnovationReportDownloadPayload,
  getInnovationReportForUser,
};
