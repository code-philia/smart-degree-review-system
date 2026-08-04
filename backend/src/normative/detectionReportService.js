const detectionTaskRepository = require('./detectionTaskRepository');

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getReportOwnerId(user) {
  return user?.username || user?.id || null;
}

async function listDetectionReportsForUser(user) {
  const ownerId = getReportOwnerId(user);
  if (!ownerId) {
    throw createHttpError(401, '请先登录后查看检测历史');
  }
  return detectionTaskRepository.listDetectionTasksByUser(ownerId);
}

async function getDetectionReportForUser(user, taskId) {
  const ownerId = getReportOwnerId(user);
  if (!ownerId) {
    throw createHttpError(401, '请先登录后查看检测报告');
  }
  if (!taskId) {
    throw createHttpError(400, '检测报告编号不能为空');
  }

  const report = await detectionTaskRepository.findDetectionTaskByIdForUser(taskId, ownerId);
  if (!report) {
    throw createHttpError(404, '检测报告不存在或无权访问');
  }
  return report;
}

function buildDownloadReportPayload(report) {
  return {
    id: report.id,
    source_filename: report.source_filename,
    created_at: report.created_at,
    status: report.status,
    severity_counts: report.severity_counts,
    rule_snapshot: report.rule_snapshot,
    issues: report.issues,
    original_text: report.original_text,
  };
}

module.exports = {
  listDetectionReportsForUser,
  getDetectionReportForUser,
  buildDownloadReportPayload,
};
