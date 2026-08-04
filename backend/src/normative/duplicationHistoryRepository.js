const { all, get, run } = require('../database');

function parseDuplicationHistoryRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    user_id: row.user_id,
    source_type: row.source_type,
    source_filename: row.source_filename || null,
    original_text: row.original_text,
    total_similarity_rate: row.total_similarity_rate,
    writing_risk_score: row.writing_risk_score,
    sample_count: row.sample_count,
    report_json: JSON.parse(row.report_json || '{}'),
    created_at: row.created_at,
  };
}

async function createDuplicationHistoryRecord(record) {
  await run(
    `INSERT INTO duplication_detection_reports (
      id,
      user_id,
      source_type,
      source_filename,
      original_text,
      total_similarity_rate,
      writing_risk_score,
      sample_count,
      report_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
    [
      record.id,
      record.user_id,
      record.source_type,
      record.source_filename || null,
      record.original_text,
      record.total_similarity_rate,
      record.writing_risk_score,
      record.sample_count,
      JSON.stringify(record.report_json || {}),
      record.created_at,
    ],
  );

  return parseDuplicationHistoryRow({
    id: record.id,
    user_id: record.user_id,
    source_type: record.source_type,
    source_filename: record.source_filename || null,
    original_text: record.original_text,
    total_similarity_rate: record.total_similarity_rate,
    writing_risk_score: record.writing_risk_score,
    sample_count: record.sample_count,
    report_json: JSON.stringify(record.report_json || {}),
    created_at: record.created_at,
  });
}

async function listDuplicationHistoryByUser(userId) {
  const rows = await all(
    `SELECT *
     FROM duplication_detection_reports
     WHERE user_id = ?
     ORDER BY created_at DESC;`,
    [userId],
  );
  return rows.map(parseDuplicationHistoryRow);
}

async function findDuplicationHistoryByIdForUser(reportId, userId) {
  const row = await get(
    `SELECT *
     FROM duplication_detection_reports
     WHERE id = ? AND user_id = ?;`,
    [reportId, userId],
  );
  return parseDuplicationHistoryRow(row);
}

module.exports = {
  createDuplicationHistoryRecord,
  findDuplicationHistoryByIdForUser,
  listDuplicationHistoryByUser,
};
