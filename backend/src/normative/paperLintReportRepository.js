const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { all, get, run } = require('../database');
const { withTransaction } = require('../database/db_runtime');

function reportsDirectory() {
  return path.resolve(process.env.PAPER_LINT_REPORTS_DIR || path.join(process.cwd(), 'data', 'paper-lint-reports'));
}

function toReport(row, { includeResult = true } = {}) {
  if (!row) return null;
  const parsedResult = JSON.parse(row.result_json);
  // A missing section has no original sentence or precise PDF location.
  for (const rule of parsedResult.rule_runs || []) {
    if (rule.rule_id === 'required_section_completeness_check') {
      for (const finding of rule.findings || []) { finding.location = null; finding.anchors = []; }
    }
  }
  const summary = parsedResult.summary || {};
  return {
    id: row.id,
    source_filename: row.source_filename,
    selected_rule_ids: JSON.parse(row.selected_rule_ids_json || '[]'),
    ...(includeResult ? { result: parsedResult } : {}),
    summary: {
      finding_count: summary.finding_count || 0,
      error_finding_count: summary.error_finding_count || 0,
      warning_finding_count: summary.warning_finding_count || 0,
      info_finding_count: summary.info_finding_count || 0,
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
  return rows.map((row) => toReport(row, { includeResult: false }));
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
  await Promise.all(rows.map(async row => {
    await fs.promises.rm(row.source_pdf_path, { force: true });
    await fs.promises.rm(`${row.source_pdf_path}.metrics.json`, { force: true }).catch(() => {});
  }));
  return uniqueIds;
}

async function deletePaperLintReportForUser(id, userId) {
  return Boolean(await deletePaperLintReportsForUser([id], userId));
}

module.exports = {
  createPaperLintReport,
  findPaperLintReportByIdForUser,
  listPaperLintReportsByUser,
  getPaperLintReportPdfFile,
  deletePaperLintReportForUser,
  deletePaperLintReportsForUser,
};
