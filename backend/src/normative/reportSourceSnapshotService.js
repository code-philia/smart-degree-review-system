const { get } = require('../database/db_runtime');

function parseJsonValue(value, fallback) {
  if (typeof value !== 'string' || !value.trim()) {
    return fallback;
  }
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function buildSourceReportFallback(row = {}) {
  return {
    title: row.report_id || '报告快照',
    original_text: '',
    findings: [],
    severity_counts: {},
    created_at: row.submitted_at || null,
  };
}

function normalizeNormativeFindings(findings) {
  if (!Array.isArray(findings)) {
    return [];
  }
  return findings.map((finding, index) => ({
    ...finding,
    finding_id: finding.finding_id || finding.rule_id || `finding-${index + 1}`,
  }));
}

async function getSourceReportSnapshot(row) {
  if (!row) {
    return buildSourceReportFallback();
  }

  if (row.source_type === 'normative') {
    const source = await get(
      `SELECT original_text, issues_json, severity_counts_json, created_at
         FROM normative_detection_tasks
        WHERE id = ? AND user_id = ?`,
      [row.report_id, row.student_id],
    );
    if (source) {
      return {
        title: row.report_id,
        original_text: source.original_text,
        findings: normalizeNormativeFindings(parseJsonValue(source.issues_json, [])),
        severity_counts: parseJsonValue(source.severity_counts_json, {}),
        created_at: source.created_at,
      };
    }
  }

  if (row.source_type === 'ai_review') {
    const source = await get(
      `SELECT thesis_title, original_text, normative_issues_json, created_at
         FROM ai_review_runs
        WHERE id = ? AND user_id = ?`,
      [row.report_id, row.student_id],
    );
    if (source) {
      return {
        title: source.thesis_title || row.report_id,
        original_text: source.original_text,
        findings: normalizeNormativeFindings(parseJsonValue(source.normative_issues_json, [])),
        severity_counts: {},
        created_at: source.created_at,
      };
    }
  }

  if (row.source_type === 'duplication') {
    const source = await get(
      `SELECT original_text, report_json, created_at
         FROM duplication_detection_reports
        WHERE id = ? AND user_id = ?`,
      [row.report_id, row.student_id],
    );
    if (source) {
      const reportJson = parseJsonValue(source.report_json, {});
      const rawMatches = Array.isArray(reportJson.matches)
        ? reportJson.matches
        : Array.isArray(reportJson.top_matches)
          ? reportJson.top_matches
          : [];
      const findings = rawMatches.map((match, index) => ({
        finding_id: `duplication-${match.sample_id || index + 1}`,
        rule_id: 'LOCAL-CORPUS-SIMILARITY',
        category: '相似片段',
        severity: Number(match.jaccard_score || 0) >= 0.5 ? 'high' : 'medium',
        line: 1,
        column: 1,
        excerpt: match.segments?.[0]?.source_excerpt || match.title || '相似片段',
        message: `与《${match.title || '本地样本'}》存在相似表达`,
        suggestion: '核对引用来源，并结合研究语境重新组织表达。',
      }));
      return {
        title: row.report_id,
        original_text: source.original_text,
        findings,
        severity_counts: reportJson.severity_counts || {},
        created_at: source.created_at,
      };
    }
  }

  if (row.source_type === 'innovation') {
    const source = await get(
      `SELECT thesis_title, input_snapshot_json, scoring_snapshot_json, created_at
         FROM innovation_assessment_snapshots
        WHERE id = ? AND user_id = ?`,
      [row.report_id, row.student_id],
    );
    if (source) {
      const inputSnapshot = parseJsonValue(source.input_snapshot_json, {});
      const scoringSnapshot = parseJsonValue(source.scoring_snapshot_json, {});
      const findings = Array.isArray(scoringSnapshot.dimensions)
        ? scoringSnapshot.dimensions.map((dimension, index) => ({
            finding_id: `innovation-${dimension.key || index + 1}`,
            rule_id: 'INNOVATION-RUBRIC',
            category: '创新性量表',
            severity: Number(dimension.level || 0) >= 4 ? 'low' : 'medium',
            line: 1,
            column: 1,
            excerpt: dimension.label || dimension.key || '创新性维度',
            message: `${dimension.label || '该维度'}量表等级为 ${dimension.level || '未填写'} 级`,
            suggestion: '结合量表证据和改进计划进行人工复核。',
          }))
        : [];
      return {
        title: source.thesis_title || row.report_id,
        original_text: inputSnapshot.research_background || inputSnapshot.text || '',
        findings,
        severity_counts: {},
        created_at: source.created_at,
      };
    }
  }

  return buildSourceReportFallback(row);
}

module.exports = {
  buildSourceReportFallback,
  getSourceReportSnapshot,
  normalizeNormativeFindings,
  parseJsonValue,
};
