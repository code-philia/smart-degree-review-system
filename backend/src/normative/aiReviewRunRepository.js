const { all, get, run } = require('../database');

function parseReviewRunRow(row) {
  if (!row) {
    return null;
  }

  return {
    id: row.id,
    user_id: row.user_id,
    thesis_title: row.thesis_title,
    template_id: row.template_id,
    source_type: row.source_type,
    source_filename: row.source_filename || null,
    original_text: row.original_text,
    section_snapshot: JSON.parse(row.section_snapshot_json || '[]'),
    reference_count: row.reference_count,
    character_count: row.character_count,
    normative_issues: JSON.parse(row.normative_issues_json || '[]'),
    score_items: JSON.parse(row.score_items_json || '[]'),
    total_score: row.total_score,
    result_label: row.result_label,
    missing_sections: JSON.parse(row.missing_sections_json || '[]'),
    rubric_snapshot: JSON.parse(row.rubric_snapshot_json || '{}'),
    created_at: row.created_at,
  };
}

async function insertAiReviewRun(reviewRun) {
  await run(
    `INSERT INTO ai_review_runs (
      id,
      user_id,
      thesis_title,
      template_id,
      source_type,
      source_filename,
      original_text,
      section_snapshot_json,
      reference_count,
      character_count,
      normative_issues_json,
      score_items_json,
      total_score,
      result_label,
      missing_sections_json,
      rubric_snapshot_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
    [
      reviewRun.id,
      reviewRun.user_id,
      reviewRun.thesis_title,
      reviewRun.template_id,
      reviewRun.source_type,
      reviewRun.source_filename || null,
      reviewRun.original_text,
      JSON.stringify(reviewRun.section_snapshot || []),
      reviewRun.reference_count,
      reviewRun.character_count,
      JSON.stringify(reviewRun.normative_issues || []),
      JSON.stringify(reviewRun.score_items || []),
      reviewRun.total_score,
      reviewRun.result_label,
      JSON.stringify(reviewRun.missing_sections || []),
      JSON.stringify(reviewRun.rubric_snapshot || {}),
      reviewRun.created_at,
    ],
  );

  return reviewRun;
}

async function listAiReviewRunsForUser(userId) {
  const rows = await all(
    `SELECT *
     FROM ai_review_runs
     WHERE user_id = ?
     ORDER BY datetime(created_at) DESC, created_at DESC;`,
    [userId],
  );
  return rows.map(parseReviewRunRow);
}

async function findAiReviewRunForUser(reviewRunId, userId) {
  const row = await get(
    `SELECT *
     FROM ai_review_runs
     WHERE id = ? AND user_id = ?;`,
    [reviewRunId, userId],
  );
  return parseReviewRunRow(row);
}

module.exports = {
  findAiReviewRunForUser,
  insertAiReviewRun,
  listAiReviewRunsForUser,
};
