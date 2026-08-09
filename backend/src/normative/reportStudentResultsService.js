const reportStudentResultsRepository = require('./reportStudentResultsRepository');
const { buildSourceReportFallback, getSourceReportSnapshot, parseJsonValue } = require('./reportSourceSnapshotService');

const ALLOWED_REPORT_STUDENT_RESULTS_ROLES = ['STUDENT'];

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function ensureStudentResultsActor(user) {
  if (!user) {
    throw createHttpError(401, '请先登录');
  }
  if (user.role !== 'STUDENT') {
    throw createHttpError(403, '仅学生可查看本人批阅结果');
  }
  return { studentId: user.id };
}

function normalizeFeedbackAnnotations(row) {
  return parseJsonValue(row.annotations_json, []);
}

function buildStudentReportResultDetail(row, historyRounds = [], report = null) {
  return {
    submission_id: row.submission_id,
    batch_id: row.batch_id,
    source_type: row.source_type,
    report_id: row.report_id,
    status: row.status,
    submitted_at: row.submitted_at,
    feedback_at: row.feedback_at,
    report: report || buildSourceReportFallback(row),
    review: {
      annotations: normalizeFeedbackAnnotations(row),
      overall_evaluation: row.overall_evaluation,
      improvement_suggestions: row.improvement_suggestions,
      submitted_at: row.feedback_at,
    },
    history_rounds: historyRounds,
  };
}

async function listStudentReportResults(user, filters = {}) {
  const { studentId } = ensureStudentResultsActor(user);
  const results = await reportStudentResultsRepository.listStudentReportResults({ studentId, filters });
  return { results };
}

async function getStudentReportResultDetail(user, submissionId) {
  const { studentId } = ensureStudentResultsActor(user);
  const row = await reportStudentResultsRepository.getStudentReportResult({
    studentId,
    submissionId,
  });
  if (!row) {
    throw createHttpError(404, '未找到可查看的批阅结果');
  }
  const report = await getSourceReportSnapshot(row);
  if (row.status === 'review_completed_feedback') {
    await reportStudentResultsRepository.markStudentFeedbackViewed({
      studentId,
      submissionId,
    });
    row.status = 'student_viewed_feedback';
  }
  const { results: historyRounds } = await listStudentReportResults(user, {
    report_id: row.report_id,
  });
  return buildStudentReportResultDetail(row, historyRounds, report);
}

async function buildStudentReportResultDownloadPayload(user, submissionId) {
  const detail = await getStudentReportResultDetail(user, submissionId);
  return {
    submission_id: detail.submission_id,
    report_summary: {
      submission_id: detail.submission_id,
      batch_id: detail.batch_id,
      source_type: detail.source_type,
      report_id: detail.report_id,
      status: detail.status,
      submitted_at: detail.submitted_at,
      feedback_at: detail.feedback_at,
    },
    annotations: detail.review.annotations,
    overall_evaluation: detail.review.overall_evaluation,
    improvement_suggestions: detail.review.improvement_suggestions,
  };
}

module.exports = {
  ALLOWED_REPORT_STUDENT_RESULTS_ROLES,
  buildStudentReportResultDownloadPayload,
  ensureStudentResultsActor,
  getStudentReportResultDetail,
  listStudentReportResults,
};
