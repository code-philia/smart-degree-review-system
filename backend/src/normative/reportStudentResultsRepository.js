const db = require('../database/db_runtime');

function buildStudentReportResultFilterClause(filters = {}) {
  const where = ['submission.student_id = ?'];
  const params = [];

  if (filters.from) {
    where.push('date(submission.created_at) >= date(?)');
    params.push(filters.from);
  }
  if (filters.to) {
    where.push('date(submission.created_at) <= date(?)');
    params.push(filters.to);
  }
  if (filters.source_type) {
    where.push('submission.source_type = ?');
    params.push(filters.source_type);
  }
  if (filters.status) {
    where.push('submission.status = ?');
    params.push(filters.status);
  }
  if (filters.report_id) {
    where.push('submission.report_id = ?');
    params.push(filters.report_id);
  }

  return { where: where.join(' AND '), params };
}

async function listStudentReportResults({ studentId, filters = {} }) {
  const { where, params } = buildStudentReportResultFilterClause(filters);
  return db.all(
    `SELECT
        submission.id AS submission_id,
        submission.batch_id,
        submission.source_type,
        submission.report_id,
        submission.status,
        submission.created_at AS submitted_at,
        feedback.locked_at AS feedback_at
       FROM report_submissions AS submission
       LEFT JOIN supervisor_review_feedback AS feedback
         ON feedback.submission_id = submission.id
      WHERE ${where}
      ORDER BY datetime(submission.created_at) DESC, submission.created_at DESC, submission.id DESC`,
    [studentId, ...params],
  );
}

async function getStudentReportResult({ studentId, submissionId }) {
  return db.get(
    `SELECT
        submission.id AS submission_id,
        submission.batch_id,
        submission.student_id,
        submission.supervisor_id,
        submission.source_type,
        submission.report_id,
        submission.status,
        submission.created_at AS submitted_at,
        feedback.annotations_json,
        feedback.overall_evaluation,
        feedback.improvement_suggestions,
        feedback.locked_at AS feedback_at
       FROM report_submissions AS submission
       INNER JOIN supervisor_review_feedback AS feedback
         ON feedback.submission_id = submission.id
      WHERE submission.student_id = ?
        AND submission.id = ?`,
    [studentId, submissionId],
  );
}

async function markStudentFeedbackViewed({ studentId, submissionId }) {
  const result = await db.run(
    `UPDATE report_submissions
        SET status = 'student_viewed_feedback'
      WHERE id = ?
        AND student_id = ?
        AND status = 'review_completed_feedback'`,
    [submissionId, studentId],
  );
  return result.changes > 0;
}

module.exports = {
  getStudentReportResult,
  listStudentReportResults,
  markStudentFeedbackViewed,
};