const fs = require('fs/promises');
const path = require('path');
const { randomUUID } = require('crypto');
const db = require('../database/db_runtime');
const { LOCAL_RULES, isLocalRuleId, runLocalFiveRules } = require('./localFiveRulePaperLintService');
const { getSixRules, isSixRuleId, runSixRules } = require('./sixRulePaperLintService');
const { getCompilerRules, isCompilerRuleId, runCompilerRules } = require('./paperCompilerService');
const { mergePaperLintResults } = require('./reviewPilotPaperLintService');

const DEFAULT_ROOT = '/opt/sjtu-archive-479';
function getArchiveRules() {
  return [...LOCAL_RULES, ...getSixRules(), ...getCompilerRules()].sort((a, b) => a.number - b.number);
}
async function runArchiveRules(pdfPath, ruleIds) {
  const localIds = ruleIds.filter(isLocalRuleId);
  const sixIds = ruleIds.filter(isSixRuleId);
  const localResult = localIds.length ? await runLocalFiveRules(pdfPath, localIds) : null;
  const sixResult = sixIds.length ? await runSixRules(pdfPath, sixIds) : null;
  const compilerIds = ruleIds.filter(isCompilerRuleId);
  const compilerResult = compilerIds.length ? await runCompilerRules(pdfPath, compilerIds) : null;
  const parts = [localResult, sixResult, compilerResult].filter(Boolean);
  return parts.length > 1 ? mergePaperLintResults(parts[0], {rule_runs:parts.slice(1).flatMap(p=>p.rule_runs)}, ruleIds) : parts[0];
}
function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}
function archiveRuleOutcome(run) {
  return run.execution_status === 'completed' && run.publication_status === 'NO_ALERT'
    ? 'no_alert'
    : run.outcome;
}
function decodeJob(row) {
  return row && { ...row, selected_rule_ids: JSON.parse(row.selected_rule_ids_json) };
}
function decodeDocument(row, full = false) {
  if (!row) return null;
  const { result_json, rule_outcomes_json, ...rest } = row;
  return {
    ...rest,
    rule_outcomes: rule_outcomes_json ? JSON.parse(rule_outcomes_json) : {},
    ...(full ? { result: result_json ? JSON.parse(result_json) : null } : {}),
  };
}
async function listArchivePdfs(root) {
  const found = [];
  async function walk(dir) {
    for (const entry of await fs.readdir(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.isFile() && entry.name.toLowerCase().endsWith('.pdf')) {
        const stat = await fs.stat(full);
        found.push({ relativePath: path.relative(root, full), filename: entry.name, sizeBytes: stat.size });
      }
    }
  }
  await walk(root);
  return found.sort((a, b) => a.relativePath.localeCompare(b.relativePath, 'zh-CN'));
}
function createArchiveScanService({
  archiveRoot = process.env.ARCHIVE_SCAN_ROOT || DEFAULT_ROOT,
  detector = runArchiveRules,
} = {}) {
  let worker = null;
  async function safePdfPath(relativePath) {
    const root = await fs.realpath(archiveRoot);
    const candidate = await fs.realpath(path.resolve(root, relativePath));
    if (!candidate.startsWith(root + path.sep) || !candidate.toLowerCase().endsWith('.pdf'))
      throw problem(404, '归档论文不存在');
    const stat = await fs.stat(candidate);
    if (!stat.isFile()) throw problem(404, '归档论文不存在');
    return candidate;
  }
  async function getJob(id) {
    const row = await db.get('SELECT * FROM archive_scan_jobs WHERE id=?', [id]);
    if (!row) throw problem(404, '扫描任务不存在');
    return decodeJob(row);
  }
  async function getDocument(jobId, documentId) {
    await getJob(jobId);
    const row = await db.get('SELECT * FROM archive_scan_documents WHERE job_id=? AND id=?', [jobId, documentId]);
    if (!row) throw problem(404, '归档论文结果不存在');
    return decodeDocument(row, true);
  }
  async function runJob(id) {
    const job = await getJob(id);
    const docs = await db.all(
      "SELECT * FROM archive_scan_documents WHERE job_id=? AND status IN ('pending','running') ORDER BY relative_path",
      [id],
    );
    for (const doc of docs) {
      try {
        await db.run("UPDATE archive_scan_documents SET status='running' WHERE id=?", [doc.id]);
        const pdf = await safePdfPath(doc.relative_path);
        const result = await detector(pdf, job.selected_rule_ids);
        const outcomes = Object.fromEntries(result.rule_runs.map((run) => [run.rule_id, archiveRuleOutcome(run)]));
        const inconclusive = Object.values(outcomes).includes('inconclusive') ? 1 : 0;
        await db.withTransaction(async (tx) => {
          await tx.run(
            "UPDATE archive_scan_documents SET status='completed', result_json=?, rule_outcomes_json=?, finding_count=?, error_message=NULL, finished_at=CURRENT_TIMESTAMP WHERE id=?",
            [JSON.stringify(result), JSON.stringify(outcomes), result.summary.finding_count, doc.id],
          );
          await tx.run(
            'UPDATE archive_scan_jobs SET completed_count=completed_count+1, finding_count=finding_count+?, inconclusive_count=inconclusive_count+? WHERE id=?',
            [result.summary.finding_count, inconclusive, id],
          );
        });
      } catch (error) {
        await db.withTransaction(async (tx) => {
          await tx.run(
            "UPDATE archive_scan_documents SET status='failed', error_message=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
            [error.message || '检测失败', doc.id],
          );
          await tx.run('UPDATE archive_scan_jobs SET failed_count=failed_count+1 WHERE id=?', [id]);
        });
      }
    }
    await db.run("UPDATE archive_scan_jobs SET status='completed', finished_at=CURRENT_TIMESTAMP WHERE id=?", [id]);
  }
  function kick(id) {
    worker = runJob(id)
      .catch(async (error) => {
        console.error('Archive scan worker failed:', error);
        await db.run("UPDATE archive_scan_jobs SET status='failed', finished_at=CURRENT_TIMESTAMP WHERE id=?", [id]);
      })
      .finally(() => {
        worker = null;
      });
  }
  async function startJob({ userId, ruleIds, externalProcessingConsent = false }) {
    if (
      !Array.isArray(ruleIds) ||
      !ruleIds.length ||
      new Set(ruleIds).size !== ruleIds.length ||
      !ruleIds.every((id) => isLocalRuleId(id) || isSixRuleId(id) || isCompilerRuleId(id))
    )
      throw problem(400, '请选择已开放的归档扫描规则');
    const selectedRules = getArchiveRules().filter((rule) => ruleIds.includes(rule.rule_id));
    if (selectedRules.some((rule) => !rule.available))
      throw problem(400, '所选规则暂不可用，请联系管理员配置检测服务');
    if (selectedRules.some(rule => rule.uses_external_model) && !externalProcessingConsent)
      throw problem(400, '运行引用语义规则前，请确认论文相关文本允许发送至外部 API');
    ruleIds = selectedRules.map((rule) => rule.rule_id);
    if (worker || (await db.get("SELECT id FROM archive_scan_jobs WHERE status='running' LIMIT 1")))
      throw problem(409, '已有归档扫描任务正在运行');
    const documents = await listArchivePdfs(archiveRoot);
    if (!documents.length) throw problem(400, '归档目录中没有 PDF 论文');
    const id = randomUUID();
    try {
      await db.withTransaction(async (tx) => {
        await tx.run(
          'INSERT INTO archive_scan_jobs (id, created_by, selected_rule_ids_json, status, total_count) VALUES (?,?,?,?,?)',
          [id, userId, JSON.stringify(ruleIds), 'running', documents.length],
        );
        for (const doc of documents)
          await tx.run(
            'INSERT INTO archive_scan_documents (id, job_id, relative_path, filename, size_bytes, status) VALUES (?,?,?,?,?,?)',
            [randomUUID(), id, doc.relativePath, doc.filename, doc.sizeBytes, 'pending'],
          );
      });
    } catch (error) {
      if (error.code?.startsWith('SQLITE_CONSTRAINT')) throw problem(409, '已有归档扫描任务正在运行');
      throw error;
    }
    kick(id);
    return getJob(id);
  }
  async function resumeJobs() {
    if (process.env.ARCHIVE_SCAN_EXTERNAL_SUPERVISOR === '1') return;
    if (worker) return;
    const active = await db.get("SELECT id FROM archive_scan_jobs WHERE status='running' LIMIT 1");
    if (active) {
      await db.run("UPDATE archive_scan_documents SET status='pending' WHERE job_id=? AND status='running'", [
        active.id,
      ]);
      kick(active.id);
    }
  }
  async function listJobs() {
    return (await db.all('SELECT * FROM archive_scan_jobs ORDER BY created_at DESC, rowid DESC')).map(decodeJob);
  }
  async function deleteJob(id) {
    await db.withTransaction(async (tx) => {
      const job = await tx.get('SELECT status FROM archive_scan_jobs WHERE id=?', [id]);
      if (!job) throw problem(404, '扫描任务不存在');
      if (job.status === 'running') throw problem(409, '正在运行的扫描任务不能删除');
      await tx.run('DELETE FROM archive_scan_jobs WHERE id=?', [id]);
    });
  }
  async function listDocuments(jobId, { ruleId, outcome, query, page = 1 } = {}) {
    await getJob(jobId);
    const findingCount = ruleId
      ? `(SELECT COALESCE(SUM(json_array_length(rule_run.value, '$.findings')), 0)
          FROM json_each(result_json, '$.rule_runs') AS rule_run
          WHERE json_extract(rule_run.value, '$.rule_id') = ?)`
      : 'finding_count';
    const rows = (
      await db.all(
        `SELECT id, job_id, relative_path, filename, size_bytes, status, ${findingCount} AS finding_count, rule_outcomes_json, error_message, finished_at FROM archive_scan_documents WHERE job_id=? ORDER BY relative_path`,
        ruleId ? [ruleId, jobId] : [jobId],
      )
    ).map((row) => decodeDocument(row));
    const filtered = rows.filter(
      (row) =>
        (!ruleId || row.rule_outcomes[ruleId]) &&
        (!outcome ||
          (outcome === 'failed'
            ? row.status === 'failed'
            : ruleId
              ? row.rule_outcomes[ruleId] === outcome
              : Object.values(row.rule_outcomes).includes(outcome))) &&
        (!query || row.relative_path.toLowerCase().includes(query.toLowerCase())),
    );
    const pageNumber = Math.max(1, Number(page) || 1);
    return {
      items: filtered.slice((pageNumber - 1) * 25, pageNumber * 25),
      total: filtered.length,
      finding_count: filtered.reduce((sum, row) => sum + row.finding_count, 0),
      page: pageNumber,
      page_size: 25,
    };
  }
  async function archivePdfPath(jobId, documentId) {
    await getJob(jobId);
    const doc = await db.get('SELECT relative_path FROM archive_scan_documents WHERE job_id=? AND id=?', [jobId, documentId]);
    if (!doc) throw problem(404, '归档论文结果不存在');
    return safePdfPath(doc.relative_path);
  }
  return {
    get rules() {
      return getArchiveRules();
    },
    archiveRoot,
    listArchivePdfs: () => listArchivePdfs(archiveRoot),
    startJob,
    resumeJobs,
    waitForIdle: async () => {
      if (worker) await worker;
    },
    listJobs,
    deleteJob,
    getJob,
    listDocuments,
    getDocument,
    archivePdfPath,
  };
}
module.exports = { createArchiveScanService, listArchivePdfs, archiveRuleOutcome };
