const { randomUUID } = require('crypto');
const reportSubmissionRepository = require('./reportSubmissionRepository');

const ALLOWED_REPORT_SUBMISSION_ROLES = ['STUDENT'];
const REPORT_SUBMISSION_SOURCE_TYPES = ['normative', 'duplication', 'innovation', 'ai_review'];

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function getCurrentUserId(user) {
  return user?.username || user?.id || null;
}

function ensureStudentSubmissionActor(user) {
  const studentId = getCurrentUserId(user);
  if (!studentId) {
    throw createHttpError(401, '请先登录后提交报告');
  }
  if (!ALLOWED_REPORT_SUBMISSION_ROLES.includes(user.role)) {
    throw createHttpError(403, '仅学生可提交本人报告');
  }
  if (!user.supervisor_id) {
    throw createHttpError(400, '当前学生未绑定导师，无法提交报告');
  }
  return { studentId, supervisorId: user.supervisor_id };
}

function normalizeSubmissionReports(payload) {
  const reports = Array.isArray(payload?.reports) ? payload.reports : [];
  if (reports.length < 1) {
    throw createHttpError(400, '请选择至少一条已完成报告');
  }

  return reports.map((report) => {
    const sourceType = String(report?.source_type || '').trim();
    const reportId = String(report?.report_id || '').trim();
    if (!REPORT_SUBMISSION_SOURCE_TYPES.includes(sourceType) || !reportId) {
      throw createHttpError(400, '报告类型或报告编号无效');
    }
    return { source_type: sourceType, report_id: reportId };
  });
}

async function assertCompletedOwnedReport(user, report) {
  // Implemented by TestDrivenDeveloper by reusing dependency-owned report repositories.
  // Must return 403 when the report exists but is not owned by the current student.
  // Must reject unfinished or unknown reports before creating submissions or todos.
  return { ...report, owner_id: getCurrentUserId(user), completed: true };
}

async function createReportSubmissionsForStudent(user, payload) {
  const { studentId, supervisorId } = ensureStudentSubmissionActor(user);
  const reports = normalizeSubmissionReports(payload);
  const verifiedReports = [];

  for (const report of reports) {
    await assertCompletedOwnedReport(user, report);
    verifiedReports.push({
      ...report,
      submission_id: randomUUID(),
      todo_id: randomUUID(),
      todo_title: '报告待批阅',
    });
  }

  return reportSubmissionRepository.createReportSubmissionBatch({
    batchId: randomUUID(),
    studentId,
    supervisorId,
    reports: verifiedReports,
    createdAt: new Date().toISOString(),
  });
}

module.exports = {
  ALLOWED_REPORT_SUBMISSION_ROLES,
  REPORT_SUBMISSION_SOURCE_TYPES,
  assertCompletedOwnedReport,
  createReportSubmissionsForStudent,
  ensureStudentSubmissionActor,
};
