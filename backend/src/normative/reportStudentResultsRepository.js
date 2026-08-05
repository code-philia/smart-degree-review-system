const db = require('../database/db_runtime');

async function listStudentReportResults({ studentId, filters = {} }) {
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
      WHERE submission.student_id = ?
      ORDER BY submission.created_at DESC`,
    [studentId],
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
  await db.run(
    `UPDATE report_submissions
        SET status = 'student_viewed_feedback'
      WHERE id = ?
        AND student_id = ?
        AND status = 'review_completed_feedback'`,
    [submissionId, studentId],
  );
}

module.exports = {
  getStudentReportResult,
  listStudentReportResults,
  markStudentFeedbackViewed,
};
