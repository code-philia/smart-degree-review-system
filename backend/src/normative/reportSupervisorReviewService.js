const { ensureSupervisorQueueActor } = require('./reportSupervisorQueueService');
const reportSupervisorReviewRepository = require('./reportSupervisorReviewRepository');
const { getSourceReportSnapshot } = require('./reportSourceSnapshotService');

const ALLOWED_REPORT_SUPERVISOR_REVIEW_ROLES = ['SUPERVISOR'];

function createHttpError(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function normalizeAnnotations(annotations) {
  if (!Array.isArray(annotations)) return [];
  return annotations
    .filter(
      (annotation) => annotation && typeof annotation.finding_id === 'string' && typeof annotation.comment === 'string',
    )
    .map((annotation) => ({
      finding_id: annotation.finding_id.trim(),
      comment: annotation.comment.trim(),
    }))
    .filter((annotation) => annotation.finding_id && annotation.comment);
}

function requireOverallEvaluation(value) {
  if (typeof value !== 'string' || !value.trim()) {
    throw createHttpError(400, '提交评阅必须至少包含一条整体评价');
  }
  return value.trim();
}

function parseFeedback(row) {
  if (!row) {
    return {
      locked: false,
      annotations: [],
      overall_evaluation: null,
      improvement_suggestions: null,
      submitted_at: null,
    };
  }

  return {
    locked: true,
    annotations: JSON.parse(row.annotations_json || '[]'),
    overall_evaluation: row.overall_evaluation,
    improvement_suggestions: row.improvement_suggestions,
    submitted_at: row.locked_at,
  };
}

function buildReviewDetail(submission, feedback, report) {
  return {
    submission_id: submission.submission_id,
    todo_id: submission.todo_id,
    student_id: submission.student_id,
    assignee_id: submission.assignee_id,
    source_type: submission.source_type,
    report_id: submission.report_id,
    status: submission.submission_status,
    todo_status: submission.todo_status,
    report,
    review: parseFeedback(feedback),
  };
}

async function getSupervisorReviewDetail(user, submissionId) {
  const { supervisorId } = ensureSupervisorQueueActor(user);
  const submission = await reportSupervisorReviewRepository.getSupervisorReviewSubmission({
    submissionId,
    supervisorId,
  });
  if (!submission) {
    throw createHttpError(403, '无权查看该提交记录');
  }
  const [feedback, report] = await Promise.all([
    reportSupervisorReviewRepository.getSupervisorReviewFeedback({
      submissionId,
    }),
    getSourceReportSnapshot(submission),
  ]);
  return buildReviewDetail(submission, feedback, report);
}

async function submitSupervisorReview(user, submissionId, payload = {}) {
  const { supervisorId } = ensureSupervisorQueueActor(user);
  const submission = await reportSupervisorReviewRepository.getSupervisorReviewSubmission({
    submissionId,
    supervisorId,
  });
  if (!submission) {
    throw createHttpError(403, '无权批阅该提交记录');
  }
  if (submission.todo_status === 'done' || submission.submission_status === 'review_completed_feedback') {
    throw createHttpError(409, '本轮批阅内容已锁定');
  }

  await reportSupervisorReviewRepository.saveSupervisorReviewFeedback({
    submissionId,
    supervisorId,
    annotations: normalizeAnnotations(payload.annotations),
    overallEvaluation: requireOverallEvaluation(payload.overall_evaluation),
    improvementSuggestions:
      typeof payload.improvement_suggestions === 'string' ? payload.improvement_suggestions.trim() : '',
    submittedAt: new Date().toISOString(),
  });

  return getSupervisorReviewDetail(user, submissionId);
}

module.exports = {
  ALLOWED_REPORT_SUPERVISOR_REVIEW_ROLES,
  getSupervisorReviewDetail,
  requireOverallEvaluation,
  submitSupervisorReview,
};
