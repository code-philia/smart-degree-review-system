const { randomUUID } = require('crypto');
const { all, get, run } = require('../database');

function parseTaskRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    user_id: row.user_id,
    status: row.status,
    source_type: row.source_type,
    source_filename: row.source_filename || null,
    original_text: row.original_text,
    rule_snapshot: JSON.parse(row.rule_snapshot_json || '[]'),
    issues: JSON.parse(row.issues_json || '[]'),
    severity_counts: JSON.parse(row.severity_counts_json || '{}'),
    created_at: row.created_at,
  };
}

async function createDetectionTask(task) {
  const now = task.created_at || new Date().toISOString();
  const id = task.id || randomUUID();

  await run(
    `INSERT INTO normative_detection_tasks (
      id,
      user_id,
      status,
      source_type,
      source_filename,
      original_text,
      rule_snapshot_json,
      issues_json,
      severity_counts_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
    [
      id,
      task.user_id,
      task.status,
      task.source_type,
      task.source_filename || null,
      task.original_text,
      JSON.stringify(task.rule_snapshot || []),
      JSON.stringify(task.issues || []),
      JSON.stringify(task.severity_counts || {}),
      now,
    ],
  );

  return {
    id,
    user_id: task.user_id,
    status: task.status,
    source_type: task.source_type,
    source_filename: task.source_filename || null,
    original_text: task.original_text,
    rule_snapshot: task.rule_snapshot || [],
    issues: task.issues || [],
    severity_counts: task.severity_counts || {},
    created_at: now,
  };
}

async function listDetectionTasksByUser(userId) {
  const rows = await all(
    `SELECT *
     FROM normative_detection_tasks
     WHERE user_id = ?
     ORDER BY created_at DESC;`,
    [userId],
  );
  return rows.map(parseTaskRow);
}

async function findDetectionTaskByIdForUser(taskId, userId) {
  const row = await get(
    `SELECT *
     FROM normative_detection_tasks
     WHERE id = ? AND user_id = ?;`,
    [taskId, userId],
  );
  return parseTaskRow(row);
}

module.exports = {
  createDetectionTask,
  listDetectionTasksByUser,
  findDetectionTaskByIdForUser,
};
