const { get } = require('../database');
const ledgerRecordsRepository = require('./ledgerRecordsRepository');

const STUDENT_QUALITY_METRIC_KEYS = ['normative', 'originality', 'innovation', 'review_base'];
const STUDENT_QUALITY_METRIC_META = {
  normative: {
    label: '规范分',
    source_type: 'normative',
    source_label: '最新规范性检测',
    detail_url_prefix: '/normative-reports/',
  },
  originality: {
    label: '原创参考分',
    source_type: 'duplication',
    source_label: '最新论文查重',
    detail_url_prefix: '/duplication-history/',
  },
  innovation: {
    label: '创新参考分',
    source_type: 'innovation',
    source_label: '最新创新性评价',
    detail_url_prefix: '/innovation-assessments/',
  },
  review_base: {
    label: '评阅基础分',
    source_type: 'ai_review',
    source_label: '最新 AI 智能评阅',
    detail_url_prefix: '/ai-review/results/',
  },
};

function createStudentQualityPortraitRepositoryError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function parseJson(value, fallback = {}) {
  try {
    return JSON.parse(value || '');
  } catch (_error) {
    return fallback;
  }
}

function roundScore(value) {
  return Math.round(Number(value) * 10) / 10;
}

function buildScopeWhere(scope, params) {
  if (scope?.role === 'STUDENT') {
    params.push(scope.student_id, scope.student_id);
    return '(u.id = ? OR u.username = ?)';
  }
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

function buildStudentWhere(studentId, params) {
  params.push(studentId, studentId);
  return '(u.id = ? OR u.username = ?)';
}

function buildDateWhere(column, filters, params) {
  const clauses = [];
  if (filters.from) {
    clauses.push(`date(${column}) >= date(?)`);
    params.push(filters.from);
  }
  if (filters.to) {
    clauses.push(`date(${column}) <= date(?)`);
    params.push(filters.to);
  }
  return clauses;
}

function scoreNormative(payload) {
  const high = Number(payload.high || 0);
  const medium = Number(payload.medium || 0);
  const low = Number(payload.low || 0);
  return roundScore(Math.max(0, 100 - high * 10 - medium * 4 - low));
}

function scoreOriginality(payload) {
  const similarityRate = Number(payload.total_similarity_rate);
  if (!Number.isFinite(similarityRate)) {
    return null;
  }
  return roundScore(Math.max(0, Math.min(100, 100 - similarityRate * 100)));
}

function scoreInnovation(payload) {
  const score = Number(payload.total_score);
  return Number.isFinite(score) ? roundScore(score) : null;
}

function scoreReviewBase(payload) {
  const totalScore = Number(payload.total_score);
  if (Number.isFinite(totalScore)) {
    return roundScore(totalScore);
  }
  const scoreItems = Array.isArray(payload.score_items) ? payload.score_items : parseJson(payload.score_items, []);
  if (!Array.isArray(scoreItems) || scoreItems.length === 0) {
    return null;
  }
  return roundScore(scoreItems.reduce((sum, item) => sum + Number(item.score || 0), 0));
}

function buildMetricResult(key, row, score) {
  const meta = STUDENT_QUALITY_METRIC_META[key];
  if (!row) {
    return {
      key,
      label: meta.label,
      score: null,
      source_record_id: null,
      source_type: meta.source_type,
      source_label: meta.source_label,
      source_created_at: null,
      detail_url: null,
    };
  }

  return {
    key,
    label: meta.label,
    score,
    source_record_id: row.id,
    source_type: meta.source_type,
    source_label: meta.source_label,
    source_created_at: row.created_at,
    detail_url: `${meta.detail_url_prefix}${row.id}`,
  };
}

async function ensureStudentInScope(scope, studentId) {
  const params = [];
  const scopeWhere = buildScopeWhere(scope, params);
  const studentWhere = buildStudentWhere(studentId, params);
  const row = await get(
    `SELECT
      u.id,
      u.username,
      u.college_id,
      u.supervisor_id
     FROM auth_users u
     WHERE ${scopeWhere} AND ${studentWhere}
     LIMIT 1;`,
    params,
  );
  if (!row) {
    throw createStudentQualityPortraitRepositoryError('STUDENT_QUALITY_PORTRAIT_FORBIDDEN', '无权查看该学生质量画像');
  }
  return row;
}

async function findLatestSourceRecord(scope, studentId, filters = {}) {
  const candidates = [];

  const normativeParams = [];
  const normativeScopeWhere = buildScopeWhere(scope, normativeParams);
  const normativeStudentWhere = buildStudentWhere(studentId, normativeParams);
  const normativeClauses = ['task.status = \'completed\'', normativeScopeWhere, normativeStudentWhere];
  buildDateWhere('task.created_at', filters, normativeParams).forEach((clause) => normativeClauses.push(clause));
  const normativeRow = await get(
    `SELECT task.id, task.source_filename, task.created_at
     FROM normative_detection_tasks task
     JOIN auth_users u ON u.id = task.user_id
     WHERE ${normativeClauses.join(' AND ')}
     ORDER BY datetime(task.created_at) DESC, task.created_at DESC
     LIMIT 1;`,
    normativeParams,
  );
  if (normativeRow) {
    candidates.push({ ...normativeRow, order_created_at: normativeRow.created_at });
  }

  const duplicationParams = [];
  const duplicationScopeWhere = buildScopeWhere(scope, duplicationParams);
  const duplicationStudentWhere = buildStudentWhere(studentId, duplicationParams);
  const duplicationClauses = [duplicationScopeWhere, duplicationStudentWhere];
  buildDateWhere('report.created_at', filters, duplicationParams).forEach((clause) => duplicationClauses.push(clause));
  const duplicationRow = await get(
    `SELECT report.id, report.source_filename, report.created_at
     FROM duplication_detection_reports report
     JOIN auth_users u ON u.id = report.user_id
     WHERE ${duplicationClauses.join(' AND ')}
     ORDER BY datetime(report.created_at) DESC, report.created_at DESC
     LIMIT 1;`,
    duplicationParams,
  );
  if (duplicationRow) {
    candidates.push({ ...duplicationRow, order_created_at: duplicationRow.created_at });
  }

  const innovationParams = [];
  const innovationScopeWhere = buildScopeWhere(scope, innovationParams);
  const innovationStudentWhere = buildStudentWhere(studentId, innovationParams);
  const innovationClauses = [innovationScopeWhere, innovationStudentWhere];
  buildDateWhere('assessment.created_at', filters, innovationParams).forEach((clause) => innovationClauses.push(clause));
  const innovationRow = await get(
    `SELECT assessment.id, assessment.thesis_title, assessment.created_at
     FROM innovation_assessment_snapshots assessment
     JOIN auth_users u ON u.id = assessment.user_id
     WHERE ${innovationClauses.join(' AND ')}
     ORDER BY datetime(assessment.created_at) DESC, assessment.created_at DESC
     LIMIT 1;`,
    innovationParams,
  );
  if (innovationRow) {
    candidates.push({ ...innovationRow, order_created_at: innovationRow.created_at });
  }

  const reviewParams = [];
  const reviewScopeWhere = buildScopeWhere(scope, reviewParams);
  const reviewStudentWhere = buildStudentWhere(studentId, reviewParams);
  const reviewClauses = [reviewScopeWhere, reviewStudentWhere];
  buildDateWhere('review.created_at', filters, reviewParams).forEach((clause) => reviewClauses.push(clause));
  const reviewRow = await get(
    `SELECT review.id, review.thesis_title, review.source_filename, review.created_at
     FROM ai_review_runs review
     JOIN auth_users u ON u.id = review.user_id
     WHERE ${reviewClauses.join(' AND ')}
     ORDER BY datetime(review.created_at) DESC, review.created_at DESC
     LIMIT 1;`,
    reviewParams,
  );
  if (reviewRow) {
    candidates.push({ ...reviewRow, order_created_at: reviewRow.created_at });
  }

  if (candidates.length === 0) {
    return null;
  }

  candidates.sort((left, right) => {
    const leftTime = new Date(left.order_created_at || left.created_at).getTime();
    const rightTime = new Date(right.order_created_at || right.created_at).getTime();
    return rightTime - leftTime;
  });

  const latest = candidates[0];
  return {
    student_id: studentId,
    thesis_title: latest.thesis_title || latest.source_filename || null,
    created_at: latest.created_at,
  };
}

async function getNormativeMetric(scope, studentId, filters) {
  const params = [];
  const scopeWhere = buildScopeWhere(scope, params);
  const studentWhere = buildStudentWhere(studentId, params);
  const clauses = ['task.status = \'completed\'', scopeWhere, studentWhere];
  buildDateWhere('task.created_at', filters, params).forEach((clause) => clauses.push(clause));
  const row = await get(
    `SELECT task.id, task.severity_counts_json, task.created_at
     FROM normative_detection_tasks task
     JOIN auth_users u ON u.id = task.user_id
     WHERE ${clauses.join(' AND ')}
     ORDER BY datetime(task.created_at) DESC, task.created_at DESC
     LIMIT 1;`,
    params,
  );
  if (!row) {
    return null;
  }
  return buildMetricResult('normative', row, scoreNormative(parseJson(row.severity_counts_json, {})));
}

async function getDuplicationMetric(scope, studentId, filters) {
  const params = [];
  const scopeWhere = buildScopeWhere(scope, params);
  const studentWhere = buildStudentWhere(studentId, params);
  const clauses = [scopeWhere, studentWhere];
  buildDateWhere('report.created_at', filters, params).forEach((clause) => clauses.push(clause));
  const row = await get(
    `SELECT report.id, report.total_similarity_rate, report.created_at
     FROM duplication_detection_reports report
     JOIN auth_users u ON u.id = report.user_id
     WHERE ${clauses.join(' AND ')}
     ORDER BY datetime(report.created_at) DESC, report.created_at DESC
     LIMIT 1;`,
    params,
  );
  if (!row) {
    return null;
  }
  return buildMetricResult('originality', row, scoreOriginality({ total_similarity_rate: row.total_similarity_rate }));
}

async function getInnovationMetric(scope, studentId, filters) {
  const params = [];
  const scopeWhere = buildScopeWhere(scope, params);
  const studentWhere = buildStudentWhere(studentId, params);
  const clauses = [scopeWhere, studentWhere];
  buildDateWhere('assessment.created_at', filters, params).forEach((clause) => clauses.push(clause));
  const row = await get(
    `SELECT assessment.id, assessment.scoring_snapshot_json, assessment.created_at, assessment.thesis_title
     FROM innovation_assessment_snapshots assessment
     JOIN auth_users u ON u.id = assessment.user_id
     WHERE ${clauses.join(' AND ')}
     ORDER BY datetime(assessment.created_at) DESC, assessment.created_at DESC
     LIMIT 1;`,
    params,
  );
  if (!row) {
    return null;
  }
  return buildMetricResult('innovation', row, scoreInnovation(parseJson(row.scoring_snapshot_json, {})));
}

async function getReviewBaseMetric(scope, studentId, filters) {
  const params = [];
  const scopeWhere = buildScopeWhere(scope, params);
  const studentWhere = buildStudentWhere(studentId, params);
  const clauses = [scopeWhere, studentWhere];
  buildDateWhere('review.created_at', filters, params).forEach((clause) => clauses.push(clause));
  const row = await get(
    `SELECT review.id, review.total_score, review.score_items_json, review.created_at, review.thesis_title, review.source_filename
     FROM ai_review_runs review
     JOIN auth_users u ON u.id = review.user_id
     WHERE ${clauses.join(' AND ')}
     ORDER BY datetime(review.created_at) DESC, review.created_at DESC
     LIMIT 1;`,
    params,
  );
  if (!row) {
    return null;
  }
  return buildMetricResult('review_base', row, scoreReviewBase({ total_score: row.total_score, score_items: row.score_items_json }));
}

function buildCompleteness(metrics) {
  const missing_metric_keys = [];
  const missing_metric_labels = [];
  metrics.forEach((metric) => {
    if (metric.score === null) {
      missing_metric_keys.push(metric.key);
      missing_metric_labels.push(metric.label);
    }
  });
  return {
    complete: missing_metric_keys.length === 0,
    missing_metric_keys,
    missing_metric_labels,
  };
}

function buildOverallScore(metrics) {
  const scores = metrics.map((metric) => metric.score);
  if (scores.some((score) => score === null)) {
    return null;
  }
  return roundScore(scores.reduce((sum, value) => sum + Number(value || 0), 0) / scores.length);
}

async function getStudentQualityPortrait(scope, studentId, filters = {}) {
  const normalizedStudentId = String(studentId || '').trim();
  if (!normalizedStudentId) {
    throw createStudentQualityPortraitRepositoryError('STUDENT_QUALITY_PORTRAIT_BAD_REQUEST', '学生画像 ID 不能为空');
  }

  const normalizedFilters = ledgerRecordsRepository.normalizeLedgerFilters({
    from: filters.from,
    to: filters.to,
    latest_only: true,
  });

  const student = await ensureStudentInScope(scope, normalizedStudentId);
  const latestSource = await findLatestSourceRecord(scope, normalizedStudentId, normalizedFilters);
  const metrics = [
    await getNormativeMetric(scope, normalizedStudentId, normalizedFilters),
    await getDuplicationMetric(scope, normalizedStudentId, normalizedFilters),
    await getInnovationMetric(scope, normalizedStudentId, normalizedFilters),
    await getReviewBaseMetric(scope, normalizedStudentId, normalizedFilters),
  ];

  const normalizedMetrics = STUDENT_QUALITY_METRIC_KEYS.map((key) => {
    const foundMetric = metrics.find((metric) => metric && metric.key === key);
    return foundMetric || buildMetricResult(key, null, null);
  });

  const completeness = buildCompleteness(normalizedMetrics);
  const overall_score = buildOverallScore(normalizedMetrics);

  return {
    student: {
      student_id: student.id,
      student_number: student.id,
      student_name: student.username,
      college_id: student.college_id || null,
      college_name: student.college_id || '全校',
      supervisor_id: student.supervisor_id || null,
      supervisor_name: student.supervisor_id || '',
      student_category: '学生',
      thesis_title: latestSource?.thesis_title || null,
    },
    metrics: normalizedMetrics,
    overall_score,
    completeness,
    generated_at: new Date().toISOString(),
  };
}

module.exports = {
  STUDENT_QUALITY_METRIC_KEYS,
  getStudentQualityPortrait,
};
