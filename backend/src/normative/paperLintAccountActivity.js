const { randomUUID } = require('crypto');
const { get, run, withTransaction } = require('../database/db_runtime');
const { TRIAL_ACCOUNTS, trialUserAllowed } = require('../auth/trialLoginPolicy');
const UPLOAD_LEASE_MS = 330000;
const ACTIVE = "status IN ('pending','running') AND cancelled_at IS NULL";

function publicActiveJob(row) {
  return row ? { job_id: row.id, user_id: row.user_id, source_filename: row.source_filename,
    status: row.status, request_id: row.request_id, selected_rule_ids: JSON.parse(row.selected_rule_ids_json),
    created_at: row.created_at, updated_at: row.updated_at, report_id: null, error_message: null } : null;
}

async function getAccountActivity(userId, query = { get }, now = Date.now()) {
  const user = await query.get('SELECT id,username,role FROM auth_users WHERE id=?', [userId]);
  if (!user) throw Object.assign(new Error('未找到当前用户'), { status: 404 });
  const limited = !trialUserAllowed(user);
  const job = await query.get(`SELECT * FROM paper_lint_jobs WHERE user_id=? AND ${ACTIVE} ORDER BY rowid LIMIT 1`, [userId]);
  const lease = await query.get('SELECT source_filename FROM paper_lint_upload_leases WHERE user_id=? AND expires_at>?', [userId, new Date(now).toISOString()])
    || await query.get('SELECT source_filename FROM paper_lint_observed_uploads WHERE user_id=? AND expires_at>? ORDER BY rowid LIMIT 1', [userId, new Date(now).toISOString()]);
  return { user_id: userId, limited, busy: Boolean(job || lease), uploading: Boolean(lease && !job),
    source_filename: job?.source_filename || lease?.source_filename || null, active_job: publicActiveJob(job) };
}

function activityConflict(activity) {
  return Object.assign(new Error('您已有一篇论文正在上传、排队或检测，请等待当前任务结束后再提交。'),
    { status: 409, code: 'PAPER_LINT_ACTIVE_TASK', activity });
}

// Keep the admission predicate inside the INSERT: independent requests and
// server processes cannot both pass a check performed before the write.
function accountAdmission(userId, uploadToken = null, now = Date.now()) {
  const accounts = Object.entries(TRIAL_ACCOUNTS);
  return { sql: `EXISTS (SELECT 1 FROM auth_users owner WHERE owner.id=? AND (
    (owner.id=owner.username AND (${accounts.map(() => '(owner.username=? AND owner.role=?)').join(' OR ')}))
    OR (NOT EXISTS (SELECT 1 FROM paper_lint_jobs WHERE user_id=owner.id AND ${ACTIVE})
      AND NOT EXISTS (SELECT 1 FROM paper_lint_upload_leases WHERE user_id=owner.id AND expires_at>? AND token IS NOT ?))))`,
    params: [userId, ...accounts.flat(), new Date(now).toISOString(), uploadToken] };
}

async function acquireUpload(userId, requestId, sourceFilename) {
  return withTransaction(async tx => {
    const now = Date.now();
    await tx.run('DELETE FROM paper_lint_upload_leases WHERE user_id=? AND expires_at<=?', [userId, new Date(now).toISOString()]);
    await tx.run('DELETE FROM paper_lint_observed_uploads WHERE user_id=? AND expires_at<=?', [userId, new Date(now).toISOString()]);
    const activity = await getAccountActivity(userId, tx, now);
    if (requestId) {
      const existing = await tx.get('SELECT id FROM paper_lint_jobs WHERE user_id=? AND request_id=?', [userId, requestId]);
      if (existing) return { existingJobId: existing.id };
    }
    if (!activity.limited) {
      const token = randomUUID();
      await tx.run('INSERT INTO paper_lint_observed_uploads (user_id,token,source_filename,expires_at) VALUES (?,?,?,?)',
        [userId, token, sourceFilename, new Date(now + UPLOAD_LEASE_MS).toISOString()]);
      return { token };
    }
    if (activity.busy) throw activityConflict(activity);
    const token = randomUUID();
    await tx.run('INSERT INTO paper_lint_upload_leases (user_id,token,source_filename,expires_at) VALUES (?,?,?,?)',
      [userId, token, sourceFilename, new Date(now + UPLOAD_LEASE_MS).toISOString()]);
    return { token };
  });
}

async function renewUpload(userId, token) {
  await run('UPDATE paper_lint_upload_leases SET expires_at=? WHERE user_id=? AND token=?',
    [new Date(Date.now() + UPLOAD_LEASE_MS).toISOString(), userId, token]);
  await run('UPDATE paper_lint_observed_uploads SET expires_at=? WHERE user_id=? AND token=?',
    [new Date(Date.now() + UPLOAD_LEASE_MS).toISOString(), userId, token]);
}
async function releaseUpload(userId, token) {
  if (token) {
    await run('DELETE FROM paper_lint_upload_leases WHERE user_id=? AND token=?', [userId, token]);
    await run('DELETE FROM paper_lint_observed_uploads WHERE user_id=? AND token=?', [userId, token]);
  }
}

module.exports = { getAccountActivity, accountAdmission, activityConflict, acquireUpload, renewUpload, releaseUpload };
