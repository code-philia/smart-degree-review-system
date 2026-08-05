const db = require('../database/db_runtime');

async function getSupervisorReviewSubmission({ submissionId, supervisorId }) {
  return db.get(
    `SELECT
        todo.id AS todo_id,
        todo.status AS todo_status,
        todo.assignee_id AS assignee_id,
        submission.id AS submission_id,
        submission.student_id AS student_id,
        submission.supervisor_id AS supervisor_id,
        submission.source_type AS source_type,
        submission.report_id AS report_id,
        submission.status AS submission_status,
        submission.created_at AS submitted_at
       FROM report_submissions AS submission
       INNER JOIN in_app_todos AS todo
          ON todo.submission_id = submission.id
      WHERE submission.id = ?
        AND todo.assignee_id = ?`,
    [submissionId, supervisorId],
  );
}

async function getSupervisorReviewFeedback({ submissionId }) {
  return db.get(
    `SELECT
        id,
        submission_id,
        supervisor_id,
        annotations_json,
        overall_evaluation,
        improvement_suggestions,
        locked_at,
        created_at
       FROM supervisor_review_feedback
      WHERE submission_id = ?`,
    [submissionId],
  );
}

async function saveSupervisorReviewFeedback({ submissionId, supervisorId, annotations, overallEvaluation, improvementSuggestions, submittedAt }) {
  return db.withTransaction(async (tx) => {
    await tx.run(
      `INSERT INTO supervisor_review_feedback (
        id, submission_id, supervisor_id, annotations_json, overall_evaluation, improvement_suggestions, locked_at, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        `review_${submissionId}`,
        submissionId,
        supervisorId,
        JSON.stringify(annotations),
        overallEvaluation,
        improvementSuggestions || null,
        submittedAt,
        submittedAt,
      ],
    );

    await tx.run(
      `UPDATE report_submissions
          SET status = 'review_completed_feedback'
        WHERE id = ?`,
      [submissionId],
    );

    await tx.run(
      `UPDATE in_app_todos
          SET status = 'done'
        WHERE submission_id = ?
          AND assignee_id = ?`,
      [submissionId, supervisorId],
    );
  });
}

module.exports = {
  getSupervisorReviewFeedback,
  getSupervisorReviewSubmission,
  saveSupervisorReviewFeedback,
};
