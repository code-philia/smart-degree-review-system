const { run } = require('../database');

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

module.exports = {
  insertInnovationAssessmentSnapshot,
};
