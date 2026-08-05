const { get, run } = require('../database');

async function insertInnovationAssessmentSnapshot(snapshot) {
  const result = await run(
    `INSERT INTO innovation_assessment_snapshots (
      id,
      user_id,
      thesis_title,
      degree_type,
      primary_discipline,
      secondary_discipline,
      research_direction,
      input_snapshot_json,
      scoring_snapshot_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
    [
      snapshot.id,
      snapshot.user_id,
      snapshot.thesis_title,
      snapshot.degree_type,
      snapshot.primary_discipline,
      snapshot.secondary_discipline,
      snapshot.research_direction,
      JSON.stringify(snapshot.input_snapshot),
      JSON.stringify(snapshot.scoring_snapshot),
      snapshot.created_at,
    ],
  );

  return { ...result, id: snapshot.id };
}

async function getInnovationAssessmentReportForUser(user, reportId) {
  const row = await get(
    `SELECT
      id,
      user_id,
      thesis_title,
      degree_type,
      primary_discipline,
      secondary_discipline,
      research_direction,
      input_snapshot_json,
      scoring_snapshot_json,
      created_at
    FROM innovation_assessment_snapshots
    WHERE id = ? AND user_id = ?;`,
    [reportId, user.id],
  );

  if (!row) {
    const error = new Error('未找到可访问的创新性量表报告');
    error.status = 404;
    throw error;
  }

  const inputSnapshot = JSON.parse(row.input_snapshot_json);
  const scoringSnapshot = JSON.parse(row.scoring_snapshot_json);

  return {
    id: row.id,
    user_id: row.user_id,
    thesis_title: row.thesis_title,
    degree_type: row.degree_type,
    primary_discipline: row.primary_discipline,
    secondary_discipline: row.secondary_discipline,
    research_direction: row.research_direction,
    input_snapshot: inputSnapshot,
    scoring_snapshot: scoringSnapshot,
    total_score: scoringSnapshot.total_score,
    grade_label: scoringSnapshot.grade_label,
    formula: scoringSnapshot.formula,
    dimensions: scoringSnapshot.dimensions,
    input: scoringSnapshot.input,
    disclaimer: '本结果为量表自评，不代替专家评审或文献查新',
    created_at: row.created_at,
  };
}

function buildInnovationAssessmentDownloadPayload(report) {
  return {
    ...report,
    exported_at: new Date().toISOString(),
  };
}

module.exports = {
  buildInnovationAssessmentDownloadPayload,
  getInnovationAssessmentReportForUser,
  insertInnovationAssessmentSnapshot,
};
