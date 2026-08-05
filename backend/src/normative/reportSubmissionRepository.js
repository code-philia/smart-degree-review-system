const db = require('../database/db_runtime');

async function createReportSubmissionBatch({ batchId, studentId, supervisorId, reports, createdAt }) {
  return db.withTransaction(async (tx) => {
    const submissions = [];
    const todos = [];

    for (const report of reports) {
      await tx.run(
        `INSERT INTO report_submissions (
          id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [
          report.submission_id,
          batchId,
          studentId,
          supervisorId,
          report.source_type,
          report.report_id,
          'submitted_pending_review',
          createdAt,
        ],
      );

      await tx.run(
        `INSERT INTO in_app_todos (
          id, submission_id, assignee_id, actor_id, status, title, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)`,
        [
          report.todo_id,
          report.submission_id,
          supervisorId,
          studentId,
          'pending',
          report.todo_title,
          createdAt,
        ],
      );

      submissions.push({
        id: report.submission_id,
        batch_id: batchId,
        student_id: studentId,
        supervisor_id: supervisorId,
        source_type: report.source_type,
        report_id: report.report_id,
        status: 'submitted_pending_review',
        created_at: createdAt,
      });
      todos.push({
        id: report.todo_id,
        submission_id: report.submission_id,
        assignee_id: supervisorId,
        actor_id: studentId,
        status: 'pending',
        title: report.todo_title,
        created_at: createdAt,
      });
    }

    return { batch_id: batchId, submissions, todos };
  });
}

module.exports = {
  createReportSubmissionBatch,
};
