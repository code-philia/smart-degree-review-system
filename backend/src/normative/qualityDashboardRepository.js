const { all } = require('../database');
const ledgerRecordsRepository = require('./ledgerRecordsRepository');

const QUALITY_METRICS = [
  { key: 'normative', label: '规范分' },
  { key: 'originality', label: '原创参考分' },
  { key: 'innovation', label: '创新参考分' },
  { key: 'review_base', label: '评阅基础分' },
];

function buildScopeWhere(scope, params) {
  if (scope?.role === 'SUPERVISOR') {
    params.push(scope.supervisor_id);
    return 'u.supervisor_id = ?';
  }
  if (scope?.role === 'COLLEGE_ADMIN') {
    params.push(scope.college_id);
    return 'u.college_id = ?';
  }
  return '1 = 1';
}

function buildQualityRowsSql(scope, filters) {
  const params = [];
  const where = [buildScopeWhere(scope, params)];

  if (filters.detection_type) {
    where.push('quality.detection_type = ?');
    params.push(filters.detection_type);
  }
  if (filters.from) {
    where.push('date(quality.created_at) >= date(?)');
    params.push(filters.from);
  }
  if (filters.to) {
    where.push('date(quality.created_at) <= date(?)');
    params.push(filters.to);
  }
  if (filters.student) {
    const keyword = `%${filters.student}%`;
    where.push(`(
      u.id LIKE ?
      OR u.username LIKE ?
      OR quality.thesis_title LIKE ?
      OR quality.source_filename LIKE ?
    )`);
    params.push(keyword, keyword, keyword, keyword);
  }
  if (filters.latest_only) {
    where.push('quality.latest_rank = 1');
  }

  const sql = `
    WITH quality AS (
      SELECT
        task.id AS source_record_id,
        task.user_id AS student_id,
        COALESCE(task.source_filename, '规范性检测') AS thesis_title,
        task.source_filename,
        'normative' AS detection_type,
        task.severity_counts_json AS payload_json,
        task.created_at,
        ROW_NUMBER() OVER (PARTITION BY task.user_id, 'normative' ORDER BY datetime(task.created_at) DESC, task.created_at DESC) AS latest_rank
      FROM normative_detection_tasks task
      WHERE task.status = 'completed'

      UNION ALL

      SELECT
        report.id AS source_record_id,
        report.user_id AS student_id,
        COALESCE(report.source_filename, '校内库查重') AS thesis_title,
        report.source_filename,
        'duplication' AS detection_type,
        json_object('total_similarity_rate', report.total_similarity_rate) AS payload_json,
        report.created_at,
        ROW_NUMBER() OVER (PARTITION BY report.user_id, 'duplication' ORDER BY datetime(report.created_at) DESC, report.created_at DESC) AS latest_rank
      FROM duplication_detection_reports report

      UNION ALL

      SELECT
        assessment.id AS source_record_id,
        assessment.user_id AS student_id,
        assessment.thesis_title,
        NULL AS source_filename,
        'innovation' AS detection_type,
        assessment.scoring_snapshot_json AS payload_json,
        assessment.created_at,
        ROW_NUMBER() OVER (PARTITION BY assessment.user_id, 'innovation' ORDER BY datetime(assessment.created_at) DESC, assessment.created_at DESC) AS latest_rank
      FROM innovation_assessment_snapshots assessment

      UNION ALL

      SELECT
        review.id AS source_record_id,
        review.user_id AS student_id,
        review.thesis_title,
        review.source_filename,
        'ai_review' AS detection_type,
        json_object('total_score', review.total_score, 'score_items', review.score_items_json) AS payload_json,
        review.created_at,
        ROW_NUMBER() OVER (PARTITION BY review.user_id, 'ai_review' ORDER BY datetime(review.created_at) DESC, review.created_at DESC) AS latest_rank
      FROM ai_review_runs review
    )
    SELECT
      quality.*,
      u.id AS student_number,
      u.username AS student_name,
      u.college_id,
      u.supervisor_id
    FROM quality
    JOIN auth_users u ON u.id = quality.student_id
    WHERE ${where.join(' AND ')}
    ORDER BY u.username ASC, datetime(quality.created_at) DESC, quality.created_at DESC;
  `;

  return { sql, params };
}

function parseJson(value, fallback = {}) {
  try {
    return JSON.parse(value || '');
  } catch (_error) {
    return fallback;
  }
}

function roundScore(value) {
  return Math.round(value * 10) / 10;
}

function scoreNormative(payload) {
  const high = Number(payload.high || 0);
  const medium = Number(payload.medium || 0);
  const low = Number(payload.low || 0);
  return Math.max(0, 100 - high * 10 - medium * 4 - low);
}

function scoreOriginality(payload) {
  const similarityRate = Number(payload.total_similarity_rate);
  if (!Number.isFinite(similarityRate)) {
    return null;
  }
  return Math.max(0, Math.min(100, 100 - similarityRate * 100));
}

function scoreInnovation(payload) {
  const score = Number(payload.total_score);
  return Number.isFinite(score) ? score : null;
}

function scoreReviewBase(payload) {
  const totalScore = Number(payload.total_score);
  if (Number.isFinite(totalScore)) {
    return totalScore;
  }
  const scoreItems = Array.isArray(payload.score_items) ? payload.score_items : parseJson(payload.score_items, []);
  if (!Array.isArray(scoreItems) || scoreItems.length === 0) {
    return null;
  }
  return scoreItems.reduce((sum, item) => sum + Number(item.score || 0), 0);
}

function scoreRow(row) {
  const payload = parseJson(row.payload_json, {});
  if (row.detection_type === 'normative') {
    return { key: 'normative', score: scoreNormative(payload) };
  }
  if (row.detection_type === 'duplication') {
    return { key: 'originality', score: scoreOriginality(payload) };
  }
  if (row.detection_type === 'innovation') {
    return { key: 'innovation', score: scoreInnovation(payload) };
  }
  if (row.detection_type === 'ai_review') {
    return { key: 'review_base', score: scoreReviewBase(payload) };
  }
  return null;
}

function average(values) {
  const validValues = values.filter((value) => value !== null && Number.isFinite(value));
  if (validValues.length === 0) {
    return null;
  }
  return roundScore(validValues.reduce((sum, value) => sum + value, 0) / validValues.length);
}

function bucketScore(score) {
  if (score >= 100) {
    return '100';
  }
  const floor = Math.max(0, Math.floor(score / 10) * 10);
  return `${floor}-${floor + 9}`;
}

function buildDistribution(scores) {
  const buckets = new Map();
  scores
    .filter((score) => score !== null && Number.isFinite(score))
    .forEach((score) => {
      const range = bucketScore(score);
      buckets.set(range, (buckets.get(range) || 0) + 1);
    });

  return Array.from(buckets.entries())
    .sort(([left], [right]) => Number(left.split('-')[0]) - Number(right.split('-')[0]))
    .map(([range, count]) => ({ range, count }));
}

function createStudent(row) {
  return {
    student_id: row.student_id,
    student_name: row.student_name || row.student_number || row.student_id,
    metricValues: {
      normative: [],
      originality: [],
      innovation: [],
      review_base: [],
    },
  };
}

async function summarizeQualityDashboard(scope, filters = {}) {
  const normalizedFilters = ledgerRecordsRepository.normalizeLedgerFilters(filters);
  const { sql, params } = buildQualityRowsSql(scope, normalizedFilters);
  const rows = await all(sql, params);
  const studentsById = new Map();

  rows.forEach((row) => {
    const scored = scoreRow(row);
    if (!scored) {
      return;
    }
    if (!studentsById.has(row.student_id)) {
      studentsById.set(row.student_id, createStudent(row));
    }
    studentsById.get(row.student_id).metricValues[scored.key].push(scored.score);
  });

  const students = Array.from(studentsById.values()).map((student) => ({
    student_id: student.student_id,
    student_name: student.student_name,
    scores: {
      normative: average(student.metricValues.normative),
      originality: average(student.metricValues.originality),
      innovation: average(student.metricValues.innovation),
      review_base: average(student.metricValues.review_base),
    },
  }));

  const sampleCount = students.length;
  const metrics = QUALITY_METRICS.map((metric) => {
    const scores = students.map((student) => student.scores[metric.key]);
    const presentScores = scores.filter((score) => score !== null && Number.isFinite(score));
    return {
      key: metric.key,
      label: metric.label,
      average_score: average(scores),
      sample_count: presentScores.length,
      missing_count: sampleCount - presentScores.length,
      distribution: buildDistribution(scores),
    };
  });

  return {
    filters: normalizedFilters,
    sample_count: sampleCount,
    metrics,
    students,
    generated_at: new Date().toISOString(),
  };
}

module.exports = {
  summarizeQualityDashboard,
};
