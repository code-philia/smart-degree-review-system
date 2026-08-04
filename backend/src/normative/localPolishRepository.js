const { get, run } = require('../database');

function parseJsonArray(value) {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    return [];
  }
}

function mapRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    user_id: row.user_id,
    original_text: row.original_text,
    polished_text: row.polished_text,
    level: row.level,
    rule_version: row.rule_version,
    changes: parseJsonArray(row.changes_json),
    diff_segments: parseJsonArray(row.diff_segments_json),
    source_result_id: row.source_result_id || null,
    retry_of: row.retry_of || null,
    created_at: row.created_at,
  };
}

async function createLocalPolishResult(result) {
  await run(
    `INSERT INTO local_polish_results (
      id,
      user_id,
      original_text,
      polished_text,
      level,
      rule_version,
      changes_json,
      diff_segments_json,
      source_result_id,
      retry_of,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      result.id,
      result.user_id,
      result.original_text,
      result.polished_text,
      result.level,
      result.rule_version,
      JSON.stringify(result.changes || []),
      JSON.stringify(result.diff_segments || []),
      result.source_result_id || null,
      result.retry_of || null,
      result.created_at,
    ],
  );

  return getLocalPolishResultForUser(result.user_id, result.id);
}

async function getLocalPolishResultForUser(userId, resultId) {
  const row = await get(
    `SELECT id, user_id, original_text, polished_text, level, rule_version, changes_json, diff_segments_json, source_result_id, retry_of, created_at
     FROM local_polish_results
     WHERE id = ? AND user_id = ?`,
    [resultId, userId],
  );
  return mapRow(row);
}

module.exports = {
  createLocalPolishResult,
  getLocalPolishResultForUser,
};
