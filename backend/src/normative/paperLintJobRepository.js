const { randomUUID } = require('crypto');
const fs = require('fs');
const path = require('path');
const { all, get, run, withTransaction } = require('../database/db_runtime');
const { estimateJobEta } = require('./paperLintEta');
const { notifyReportEmailReady } = require('../notifications/reportEmailWakeup');
const { quotaAdmission, quotaExceeded } = require('./paperLintQuota');

function jobsDirectory() {
  return path.resolve(process.env.PAPER_LINT_JOBS_DIR || path.join(process.cwd(), 'data', 'paper-lint-jobs'));
}

function publicJob(row) {
  if (!row) return null;
  return {
    job_id: row.id, status: row.cancelled_at ? 'cancelled' : row.status, report_id: row.report_id || null,
    error_message: row.error_message || null, created_at: row.created_at,
    updated_at: row.updated_at,
    user_id: row.user_id, source_filename: row.source_filename,
    selected_rule_ids: JSON.parse(row.selected_rule_ids_json || '[]'),
    queue_position: row.status === 'pending' && !row.cancelled_at ? Number(row.queue_position || 1) : 0,
    progress: row.progress_json ? (() => { try { return JSON.parse(row.progress_json); } catch { return null; } })() : null,
  };
}

async function createJob({ userId, sourceFilename, pdfBuffer, selectedRuleIds, externalProcessingConsent, requestId = null, reuse = null, notificationLocale = 'zh' }) {
  if (requestId) {
    const existing = await get('SELECT id FROM paper_lint_jobs WHERE user_id = ? AND request_id = ?', [userId, requestId]);
    if (existing) return existing.id;
  }
  const id = randomUUID();
  const directory = jobsDirectory();
  const pdfPath = path.join(directory, id + '.pdf');
  await fs.promises.mkdir(directory, { recursive: true, mode: 0o700 });
  await fs.promises.writeFile(pdfPath, pdfBuffer, { flag: 'wx', mode: 0o600 });
  try {
    const now = new Date().toISOString();
    const guard = quotaAdmission(userId, now);
    const inserted = await run(`INSERT INTO paper_lint_jobs (id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,external_consent,request_id,status,attempts,created_at,updated_at,reuse_json,notification_locale,notify_completion)
      SELECT ?,?,?,?,?,?,?,?,?,?,?,?,?,1 WHERE (${guard.sql})`,
      [id, userId, sourceFilename, pdfPath, JSON.stringify(selectedRuleIds),
        externalProcessingConsent ? 1 : 0, requestId, 'pending', 0, now, now, reuse ? JSON.stringify(reuse) : null,
        notificationLocale === 'en' ? 'en' : 'zh', ...guard.params]);
    if (!inserted.changes) {
      await fs.promises.rm(pdfPath, { force: true });
      if (requestId) {
        const existing = await get('SELECT id FROM paper_lint_jobs WHERE user_id = ? AND request_id = ?', [userId, requestId]);
        if (existing) return existing.id;
      }
      throw await quotaExceeded(userId);
    }
  } catch (error) {
    await fs.promises.rm(pdfPath, { force: true });
    if (requestId && String(error?.message || '').includes('UNIQUE')) {
      const existing = await get('SELECT id FROM paper_lint_jobs WHERE user_id = ? AND request_id = ?', [userId, requestId]);
      if (existing) return existing.id;
    }
    throw error;
  }
  return id;
}

async function getJob(id) {
  return get('SELECT * FROM paper_lint_jobs WHERE id = ?', [id]);
}

async function getJobForUser(id, userId) {
  const row = await get(`SELECT job.*, 1 + (SELECT count(*) FROM paper_lint_jobs other
    WHERE other.id != job.id AND other.cancelled_at IS NULL
      AND (other.status = 'running' OR (other.status = 'pending' AND other.rowid < job.rowid))) AS queue_position
    FROM paper_lint_jobs job WHERE job.id = ? AND job.user_id = ?`, [id, userId]);
  return row ? {...publicJob(row),eta:await estimateJobEta(row)} : null;
}

async function recoverJobs() {
  await run("UPDATE paper_lint_jobs SET status = 'pending', updated_at = ? WHERE status = 'running'",
    [new Date().toISOString()]);
  return all("SELECT id FROM paper_lint_jobs WHERE status = 'pending' ORDER BY rowid");
}

async function claimJob(id) {
  const now=new Date().toISOString();
  const changed = await run("UPDATE paper_lint_jobs SET status = 'running', attempts = attempts + 1, updated_at = ?, started_at = ?, progress_json = NULL WHERE id = ? AND status = 'pending'",
    [now,now,id]);
  return changed.changes > 0;
}

async function updateProgress(id, progress) {
  await run("UPDATE paper_lint_jobs SET progress_json = ?, updated_at = ? WHERE id = ? AND status = 'running'",
    [JSON.stringify(progress || null), new Date().toISOString(), id]);
}

async function completeJob(id, reportId) {
  let notificationQueued=false;
  const completed=await withTransaction(async tx => {
    const now = new Date().toISOString();
    const changed = await tx.run("UPDATE paper_lint_jobs SET status = 'completed', report_id = ?, error_message = NULL, updated_at = ? WHERE id = ? AND status = 'running' AND cancelled_at IS NULL",
      [reportId, now, id]);
    if (!changed.changes) return false;
    const queued=await tx.run(`INSERT OR IGNORE INTO report_email_outbox
      (job_id,user_id,report_id,status,attempts,next_attempt_at,created_at,updated_at)
      SELECT id,user_id,report_id,'pending',0,?,?,? FROM paper_lint_jobs WHERE id=? AND notify_completion=1`, [now,now,now,id]);
    notificationQueued=queued.changes>0;
    return true;
  });
  if (notificationQueued) notifyReportEmailReady();
  return completed;
}

async function cancelJobForUser(id, userId) {
  const now = new Date().toISOString();
  // Retain the existing terminal-state CHECK while recording cancellation explicitly.
  await run("UPDATE paper_lint_jobs SET status = 'failed', cancelled_at = ?, error_message = NULL, updated_at = ? WHERE id = ? AND user_id = ? AND status IN ('pending','running')",
    [now, now, id, userId]);
  return get('SELECT * FROM paper_lint_jobs WHERE id = ? AND user_id = ?', [id, userId]);
}

async function failJob(id, message) {
  await run("UPDATE paper_lint_jobs SET status = 'failed', error_message = ?, updated_at = ? WHERE id = ? AND status = 'running'",
    [message, new Date().toISOString(), id]);
}

module.exports = { createJob, getJob, getJobForUser, recoverJobs, claimJob, updateProgress, completeJob, cancelJobForUser, failJob, publicJob };
