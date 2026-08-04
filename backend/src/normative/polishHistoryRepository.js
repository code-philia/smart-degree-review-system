const { all, get } = require('../database');

function parseJsonArray(value) {
  try {
    const parsed = JSON.parse(value || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch (_error) {
    return [];
  }
}

function mapWholeRow(row) {
  if (!row) {
    return null;
  }

  const changes = parseJsonArray(row.changes_json);
  return {
    id: row.id,
    user_id: row.user_id,
    polish_type: 'whole',
    source_type: row.source_type,
    source_filename: row.source_filename || null,
    document_name: row.source_filename || '全文润色',
    original_text: row.original_text,
    polished_text: row.polished_text,
    level: row.level,
    changes,
    diff_segments: [],
    change_count: changes.length,
    created_at: row.created_at,
  };
}

function mapLocalRow(row) {
  if (!row) {
    return null;
  }

  const changes = parseJsonArray(row.changes_json);
  return {
    id: row.id,
    user_id: row.user_id,
    polish_type: 'local',
    source_type: 'paste',
    source_filename: null,
    document_name: '局部润色',
    original_text: row.original_text,
    polished_text: row.polished_text,
    level: row.level,
    rule_version: row.rule_version,
    changes,
    diff_segments: parseJsonArray(row.diff_segments_json),
    source_result_id: row.source_result_id || null,
    retry_of: row.retry_of || null,
    change_count: changes.length,
    created_at: row.created_at,
  };
}

async function listPolishHistoryByUser(userId) {
  const rows = await all(
    `SELECT id, user_id, 'whole' AS polish_type, source_type, source_filename, original_text, polished_text, level,
            changes_json, NULL AS diff_segments_json, NULL AS rule_version, NULL AS source_result_id, NULL AS retry_of, created_at
     FROM whole_polish_results
     WHERE user_id = ?
     UNION ALL
     SELECT id, user_id, 'local' AS polish_type, 'paste' AS source_type, NULL AS source_filename, original_text, polished_text, level,
            changes_json, diff_segments_json, rule_version, source_result_id, retry_of, created_at
     FROM local_polish_results
     WHERE user_id = ?
     ORDER BY created_at DESC;`,
    [userId, userId],
  );

  return rows.map((row) => (row.polish_type === 'whole' ? mapWholeRow(row) : mapLocalRow(row)));
}

async function findPolishHistoryRecordForUser(polishType, resultId, userId) {
  if (polishType === 'whole') {
    const row = await get(
      `SELECT id, user_id, source_type, source_filename, original_text, polished_text, level, changes_json, created_at
       FROM whole_polish_results
       WHERE id = ? AND user_id = ?;`,
      [resultId, userId],
    );
    return mapWholeRow(row);
  }

  if (polishType === 'local') {
    const row = await get(
      `SELECT id, user_id, original_text, polished_text, level, rule_version, changes_json, diff_segments_json, source_result_id, retry_of, created_at
       FROM local_polish_results
       WHERE id = ? AND user_id = ?;`,
      [resultId, userId],
    );
    return mapLocalRow(row);
  }

  return null;
}

module.exports = {
  findPolishHistoryRecordForUser,
  listPolishHistoryByUser,
};
