const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { all, get, run } = require('../database');
const { withTransaction } = require('../database/db_runtime');
const { removeBrowserPdf } = require('./browserPdf');
const { hydratePaperLintEvidenceLocations } = require('./paperLintEvidenceLocations');
const presentation = import('../../../shared/paper-lint-presentation.mjs');
const { isRetiredPaperLintRule } = require('../../../shared/paper-lint-rule-policy.mjs');

function reportsDirectory() {
  return path.resolve(process.env.PAPER_LINT_REPORTS_DIR || path.join(process.cwd(), 'data', 'paper-lint-reports'));
}

async function toReport(row, { includeResult = true } = {}) {
  if (!row) return null;
  const { visiblePaperLintResult } = await presentation;
  const parsedResult = visiblePaperLintResult(JSON.parse(row.result_json));
  if (includeResult) await hydratePaperLintEvidenceLocations(parsedResult, row.source_pdf_path);
  // A missing section has no original sentence or precise PDF location.
  for (const rule of parsedResult.rule_runs || []) {
    // Update legacy default copy in responses only; stored findings, source
    // locations and user-specific suggestions retain their original values.
    if (rule.rule_id === 'sjtu_rule_31') {
      for (const finding of rule.findings || []) {
        if (finding.message === '文献类型或载体标记不在国标代码表中') {
          finding.message = '按最新参考文献标准GB/T 7714-2025，文献类型或载体标记不在国标代码表中';
        }
        if (finding.suggestion === '请按实际著录资源核对并补齐类型标记；期刊用[J]、会议论文用[C]等，不能仅凭访问网址改变资源类型。') {
          finding.suggestion = '可按最新国家标准根据实际著录资源核对并补齐类型标记，所有参考文献标准统一用GB/T 7714-2025或GB/T 7714-2015，该检测项为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新';
        }
      }
    }
    if (rule.rule_id === 'required_section_completeness_check') {
      for (const finding of rule.findings || []) { finding.location = null; finding.anchors = []; }
    }
  }
  const { displayedReportSummary, referenceInfoFindings, referenceResourcesUnavailable, referenceResourceMessage } = await presentation;
  for (const rule of parsedResult.rule_runs || []) {
    if (rule.rule_id === 'sjtu_rule_32') {
      const resourceMessage = referenceResourceMessage(rule);
      if (resourceMessage) rule.message = resourceMessage;
      rule.findings = referenceInfoFindings(rule);
      rule.severity = 'info';
      const unresolved = rule.findings.filter(f => f.reference_review === 'insufficient_evidence').length;
      if (unresolved && !referenceResourcesUnavailable(rule) && rule.execution_status === 'completed') {
        const suspected = rule.findings.length - unresolved;
        rule.message = [suspected ? `发现 ${suspected} 条疑似不存在的引用，请逐条人工复核。` : null,
          `${unresolved} 条引用核验证据不足，请人工核查（提示）。`].filter(Boolean).join(' ');
      }
    }
  }
  const summary = displayedReportSummary(parsedResult);
  parsedResult.summary = summary;
  return {
    id: row.id,
    source_filename: row.source_filename,
    // History classification uses original selections; detail/rerun scope excludes retired checks.
    selected_rule_ids: JSON.parse(row.selected_rule_ids_json || '[]').filter(id => !includeResult || !isRetiredPaperLintRule(id)),
    ...(includeResult ? { result: parsedResult } : {}),
    summary: {
      finding_count: summary.finding_count || 0,
      error_finding_count: summary.error_finding_count || 0,
      warning_finding_count: summary.warning_finding_count || 0,
      info_finding_count: summary.info_finding_count || 0,
      execution_warning_count: summary.execution_warning_count || 0,
      rule_count: summary.rule_count || 0,
      unsupported_rule_count: summary.unsupported_rule_count || 0,
      error_rule_count: summary.error_rule_count || 0,
      ruleset_label: parsedResult.ruleset?.version_label || null,
    },
    created_at: row.created_at,
  };
}

async function createPaperLintReport({ userId, sourceFilename, pdfBuffer, selectedRuleIds, result, reportId }) {
  const id = reportId || randomUUID();
  if (reportId) {
    const existing = await findPaperLintReportByIdForUser(id, userId);
    if (existing) return existing;
  }
  const directory = reportsDirectory();
  const pdfPath = path.join(directory, `${id}.pdf`);
  await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
  await fs.promises.writeFile(pdfPath, pdfBuffer, { flag: reportId ? 'w' : 'wx', mode: 0o600 });
  try {
    await run(
      `INSERT OR IGNORE INTO paper_lint_reports (
        id, user_id, source_filename, source_pdf_path, selected_rule_ids_json, result_json, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?);`,
      [id, userId, sourceFilename, pdfPath, JSON.stringify(selectedRuleIds), JSON.stringify(result), new Date().toISOString()],
    );
  } catch (error) {
    await fs.promises.rm(pdfPath, { force: true });
    throw error;
  }
  return findPaperLintReportByIdForUser(id, userId);
}

async function listPaperLintReportsByUser(userId) {
  const rows = await all(
    `SELECT * FROM paper_lint_reports WHERE user_id = ? ORDER BY created_at DESC;`,
    [userId],
  );
  return Promise.all(rows.map((row) => toReport(row, { includeResult: false })));
}

async function findPaperLintReportByIdForUser(id, userId) {
  const row = await get(`SELECT * FROM paper_lint_reports WHERE id = ? AND user_id = ?;`, [id, userId]);
  return toReport(row);
}

async function getPaperLintReportPdfFile(id, userId) {
  const row = await get(
    `SELECT source_filename, source_pdf_path FROM paper_lint_reports WHERE id = ? AND user_id = ?;`,
    [id, userId],
  );
  if (!row) return null;
  try {
    const stat = await fs.promises.stat(row.source_pdf_path);
    return { source_filename: row.source_filename, path: stat.isFile() ? row.source_pdf_path : null };
  } catch (error) {
    if (error.code === 'ENOENT') return { source_filename: row.source_filename, path: null };
    throw error;
  }
}

async function deletePaperLintReportsForUser(ids, userId) {
  const uniqueIds = [...new Set(ids)];
  const placeholders = uniqueIds.map(() => '?').join(',');
  const rows = await withTransaction(async (tx) => {
    const owned = await tx.all(`SELECT id, source_pdf_path FROM paper_lint_reports WHERE user_id = ? AND id IN (${placeholders})`, [userId, ...uniqueIds]);
    if (owned.length !== uniqueIds.length) return null;
    await tx.run(`DELETE FROM paper_lint_reports WHERE user_id = ? AND id IN (${placeholders})`, [userId, ...uniqueIds]);
    return owned;
  });
  if (!rows) return null;
  await require('./feedbackArchive').refreshFeedbackArchiveSafely();
  await Promise.all(rows.map(async row => {
    await fs.promises.rm(row.source_pdf_path, { force: true });
    await removeBrowserPdf(row.source_pdf_path);
    await fs.promises.rm(`${row.source_pdf_path}.metrics.json`, { force: true }).catch(() => {});
  }));
  return uniqueIds;
}

async function deletePaperLintReportForUser(id, userId) {
  return Boolean(await deletePaperLintReportsForUser([id], userId));
}

module.exports = {
  toPaperLintReport: toReport,
  createPaperLintReport,
  findPaperLintReportByIdForUser,
  listPaperLintReportsByUser,
  getPaperLintReportPdfFile,
  deletePaperLintReportForUser,
  deletePaperLintReportsForUser,
};
