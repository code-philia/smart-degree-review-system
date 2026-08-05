const { randomUUID } = require('crypto');
const { get } = require('../database');
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
  const supervisorId = user?.supervisor_id || user?.supervisorId || null;
  if (!studentId) {
    throw createHttpError(401, '请先登录后提交报告');
  }
  if (!ALLOWED_REPORT_SUBMISSION_ROLES.includes(user.role)) {
    throw createHttpError(403, '仅学生可提交本人报告');
  }
  if (!supervisorId) {
    throw createHttpError(400, '当前学生未绑定导师，无法提交报告');
  }
  return { studentId, supervisorId };
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

const REPORT_LOOKUPS = {
  normative: {
    table: 'normative_detection_tasks',
    completeWhere: "status = 'completed'",
  },
  duplication: {
    table: 'duplication_detection_reports',
    completeWhere: '1 = 1',
  },
  innovation: {
    table: 'innovation_assessment_snapshots',
    completeWhere: '1 = 1',
  },
  ai_review: {
    table: 'ai_review_runs',
    completeWhere: '1 = 1',
  },
};

async function findReportBySourceType(report) {
  const lookup = REPORT_LOOKUPS[report.source_type];
  if (!lookup) {
    return null;
  }
  return get(
    `SELECT id, user_id AS userId
       FROM ${lookup.table}
      WHERE id = ? AND ${lookup.completeWhere}`,
    [report.report_id],
  );
}

async function assertCompletedOwnedReport(user, report) {
  const studentId = getCurrentUserId(user);
  const row = await findReportBySourceType(report);
  if (!row) {
    throw createHttpError(400, '所选报告不存在或尚未完成');
  }
  if (row.userId !== studentId) {
    throw createHttpError(403, '不能提交他人报告');
  }
  return { ...report, owner_id: studentId, completed: true };
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
  normalizeSubmissionReports,
};
