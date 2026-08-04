const { randomUUID } = require('crypto');
const duplicationHistoryRepository = require('./duplicationHistoryRepository');

const ALLOWED_DUPLICATION_HISTORY_ROLES = ['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN'];

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getOwnerId(user) {
  return user?.username || user?.id || null;
}

function ensureCanAccessDuplicationHistory(user) {
  const ownerId = getOwnerId(user);
  if (!ownerId) {
    throw createHttpError(401, '请先登录后查看相似度检测历史');
  }
  if (!ALLOWED_DUPLICATION_HISTORY_ROLES.includes(user.role)) {
    throw createHttpError(403, '当前角色无权查看相似度检测历史');
  }
  return ownerId;
}

async function createDuplicationHistoryFromDetection(user, request, detectionResult) {
  const ownerId = ensureCanAccessDuplicationHistory(user);
  return duplicationHistoryRepository.createDuplicationHistoryRecord({
    id: randomUUID(),
    user_id: ownerId,
    source_type: detectionResult.source_type,
    source_filename: detectionResult.source_filename || null,
    original_text: request.text,
    total_similarity_rate: detectionResult.total_similarity_rate,
    writing_risk_score: detectionResult.risk?.score || 0,
    sample_count: detectionResult.sample_count,
    report_json: detectionResult,
    created_at: new Date().toISOString(),
  });
}

async function listDuplicationHistoryForUser(user) {
  const ownerId = ensureCanAccessDuplicationHistory(user);
  return duplicationHistoryRepository.listDuplicationHistoryByUser(ownerId);
}

async function getDuplicationReportForUser(user, reportId) {
  const ownerId = ensureCanAccessDuplicationHistory(user);
  if (!reportId) {
    throw createHttpError(400, '相似度报告编号不能为空');
  }

  const report = await duplicationHistoryRepository.findDuplicationHistoryByIdForUser(reportId, ownerId);
  if (!report) {
    throw createHttpError(404, '相似度报告不存在或无权访问');
  }
  return report;
}

function buildDuplicationDownloadPayload(report) {
  return {
    id: report.id,
    source_filename: report.source_filename,
    total_similarity_rate: report.total_similarity_rate,
    writing_risk_score: report.writing_risk_score,
    sample_count: report.sample_count,
    created_at: report.created_at,
    report: report.report_json,
    original_text: report.original_text,
  };
}

module.exports = {
  ALLOWED_DUPLICATION_HISTORY_ROLES,
  buildDuplicationDownloadPayload,
  createDuplicationHistoryFromDetection,
  ensureCanAccessDuplicationHistory,
  getDuplicationReportForUser,
  listDuplicationHistoryForUser,
};
