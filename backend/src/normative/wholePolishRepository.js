const { get, run } = require('../database');

function parseChanges(changesJson) {
  try {
    const parsed = JSON.parse(changesJson || '[]');
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
    source_type: row.source_type,
    source_filename: row.source_filename || null,
    original_text: row.original_text,
    polished_text: row.polished_text,
    level: row.level,
    changes: parseChanges(row.changes_json),
    created_at: row.created_at,
  };
}

async function createWholePolishResult(result) {
  await run(
    `INSERT INTO whole_polish_results (
      id,
      user_id,
      source_type,
      source_filename,
      original_text,
      polished_text,
      level,
      changes_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      result.id,
      result.user_id,
      result.source_type,
      result.source_filename || null,
      result.original_text,
      result.polished_text,
      result.level,
      JSON.stringify(result.changes || []),
      result.created_at,
    ],
  );

  return getWholePolishResultForUser(result.user_id, result.id);
}

async function getWholePolishResultForUser(userId, resultId) {
  const row = await get(
    `SELECT id, user_id, source_type, source_filename, original_text, polished_text, level, changes_json, created_at
     FROM whole_polish_results
     WHERE id = ? AND user_id = ?`,
    [resultId, userId],
  );
  return mapRow(row);
}

module.exports = {
  createWholePolishResult,
  getWholePolishResultForUser,
};
