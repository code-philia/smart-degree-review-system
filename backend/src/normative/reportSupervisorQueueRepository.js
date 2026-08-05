const db = require('../database/db_runtime');

function buildQueueFilters(supervisorId, filters = {}) {
  const where = ['todo.assignee_id = ?'];
  const params = [supervisorId];

  if (filters.student_id) {
    where.push('submission.student_id = ?');
    params.push(filters.student_id);
  }
  if (filters.source_type) {
    where.push('submission.source_type = ?');
    params.push(filters.source_type);
  }
  if (filters.status) {
    where.push('todo.status = ?');
    params.push(filters.status);
  }

  return { where: where.join(' AND '), params };
}

async function countIncompleteSupervisorReviewTodos({ supervisorId }) {
  const row = await db.get(
    `SELECT COUNT(*) AS unread_count
       FROM in_app_todos
      WHERE assignee_id = ?
        AND status != 'done'`,
    [supervisorId],
  );

  return { unread_count: Number(row?.unread_count || 0) };
}

async function listSupervisorReviewTodos({ supervisorId, filters = {} }) {
  const { where, params } = buildQueueFilters(supervisorId, filters);
  const records = await db.all(
    `SELECT
        todo.id AS todo_id,
        todo.submission_id AS submission_id,
        submission.student_id AS student_id,
        todo.assignee_id AS assignee_id,
        submission.source_type AS source_type,
        submission.report_id AS report_id,
        submission.status AS submission_status,
        todo.status AS todo_status,
        todo.title AS title,
        todo.created_at AS created_at
       FROM in_app_todos AS todo
       INNER JOIN report_submissions AS submission
          ON submission.id = todo.submission_id
      WHERE ${where}
      ORDER BY
        CASE WHEN todo.status = 'pending' THEN 0 ELSE 1 END ASC,
        todo.created_at DESC`,
    params,
  );
  const badge = await countIncompleteSupervisorReviewTodos({ supervisorId });

  return { records, unread_count: badge.unread_count };
}

module.exports = {
  countIncompleteSupervisorReviewTodos,
  listSupervisorReviewTodos,
};
