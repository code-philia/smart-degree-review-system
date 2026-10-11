const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { all, get, run } = require('../database/db_runtime');

function jobsDirectory() {
  return path.resolve(process.env.PAPER_LINT_JOBS_DIR || path.join(process.cwd(), 'data', 'paper-lint-jobs'));
}

function publicJob(row) {
  if (!row) return null;
  return {
    job_id: row.id, status: row.status, report_id: row.report_id || null,
    error_message: row.error_message || null, created_at: row.created_at,
    updated_at: row.updated_at,
  };
}

async function createJob({ userId, sourceFilename, pdfBuffer, selectedRuleIds, externalProcessingConsent }) {
  const id = randomUUID();
  const directory = jobsDirectory();
  const pdfPath = path.join(directory, id + '.pdf');
  await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
  await fs.promises.writeFile(pdfPath, pdfBuffer, { flag: 'wx', mode: 0o600 });
  try {
    await run('INSERT INTO paper_lint_jobs (id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,external_consent,status,attempts,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
      [id, userId, sourceFilename, pdfPath, JSON.stringify(selectedRuleIds),
        externalProcessingConsent ? 1 : 0, 'pending', 0, new Date().toISOString(), new Date().toISOString()]);
  } catch (error) {
    await fs.promises.rm(pdfPath, { force: true });
    throw error;
  }
  return id;
}

async function getJob(id) {
  return get('SELECT * FROM paper_lint_jobs WHERE id = ?', [id]);
}

async function getJobForUser(id, userId) {
  return publicJob(await get('SELECT * FROM paper_lint_jobs WHERE id = ? AND user_id = ?', [id, userId]));
}

async function recoverJobs() {
  await run("UPDATE paper_lint_jobs SET status = 'pending', updated_at = ? WHERE status = 'running'",
    [new Date().toISOString()]);
  return all("SELECT id FROM paper_lint_jobs WHERE status = 'pending' ORDER BY created_at");
}

async function claimJob(id) {
  const changed = await run("UPDATE paper_lint_jobs SET status = 'running', attempts = attempts + 1, updated_at = ? WHERE id = ? AND status = 'pending'",
    [new Date().toISOString(), id]);
  return changed.changes > 0;
}

async function completeJob(id, reportId) {
  await run("UPDATE paper_lint_jobs SET status = 'completed', report_id = ?, error_message = NULL, updated_at = ? WHERE id = ? AND status = 'running'",
    [reportId, new Date().toISOString(), id]);
}

async function failJob(id, message) {
  await run("UPDATE paper_lint_jobs SET status = 'failed', error_message = ?, updated_at = ? WHERE id = ? AND status = 'running'",
    [message, new Date().toISOString(), id]);
}

module.exports = { createJob, getJob, getJobForUser, recoverJobs, claimJob, completeJob, failJob, publicJob };
