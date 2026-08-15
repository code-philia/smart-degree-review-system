const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { all, get, run } = require('../database');

function reportsDirectory() {
  return path.resolve(process.env.PAPER_LINT_REPORTS_DIR || path.join(process.cwd(), 'data', 'paper-lint-reports'));
}

function toReport(row, { includeResult = true } = {}) {
  if (!row) return null;
  const parsedResult = JSON.parse(row.result_json);
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
      ruleset_label: parsedResult.ruleset?.version_label || null,
    },
    created_at: row.created_at,
  };
}

async function createPaperLintReport({ userId, sourceFilename, pdfBuffer, selectedRuleIds, result }) {
  const id = randomUUID();
  const directory = reportsDirectory();
  const pdfPath = path.join(directory, `${id}.pdf`);
  await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
  await fs.promises.writeFile(pdfPath, pdfBuffer, { flag: 'wx', mode: 0o600 });
  try {
    await run(
      `INSERT INTO paper_lint_reports (
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

async function readPaperLintReportPdf(id, userId) {
  const row = await get(
    `SELECT source_filename, source_pdf_path FROM paper_lint_reports WHERE id = ? AND user_id = ?;`,
    [id, userId],
  );
  if (!row) return null;
  try {
    return { source_filename: row.source_filename, content: await fs.promises.readFile(row.source_pdf_path) };
  } catch (error) {
    if (error.code === 'ENOENT') return { source_filename: row.source_filename, content: null };
    throw error;
  }
}

module.exports = {
  createPaperLintReport,
  findPaperLintReportByIdForUser,
  listPaperLintReportsByUser,
  readPaperLintReportPdf,
};
