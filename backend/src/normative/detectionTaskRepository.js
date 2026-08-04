const { randomUUID } = require('crypto');
const { run } = require('../database');

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

module.exports = {
  createDetectionTask,
};
