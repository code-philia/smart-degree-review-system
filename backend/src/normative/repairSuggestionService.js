const { randomUUID } = require('crypto');
const db = require('../database/db_runtime');
const { buildLegacyRepairRequest } = require('./legacyRepairAdapter');

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function decodeDocument(row) {
  if (!row) return null;
  return { ...row, result: row.result_json ? JSON.parse(row.result_json) : null };
}

async function getArchiveFinding(jobId, documentId, ruleId, findingId) {
  const [job, row] = await Promise.all([
    db.get('SELECT * FROM archive_scan_jobs WHERE id=?', [jobId]),
    db.get('SELECT * FROM archive_scan_documents WHERE job_id=? AND id=?', [jobId, documentId]),
  ]);
  if (!job || !row) throw problem(404, '归档论文或扫描任务不存在');
  const document = decodeDocument(row);
  const ruleRun = document.result?.rule_runs?.find((run) => run.rule_id === ruleId);
  const finding = ruleRun?.findings?.find((item) => item.finding_id === findingId);
  if (!ruleRun || !finding) throw problem(404, '归档告警不存在');
  return { job, document, ruleRun, finding };
}

async function buildArchiveRepairRequest({ jobId, documentId, ruleId, findingId }) {
  return buildLegacyRepairRequest(await getArchiveFinding(jobId, documentId, ruleId, findingId));
}

async function findRepairSuggestion(request, { model, modelVersion, promptVersion }) {
  const row = await db.get(
    `SELECT response_json FROM repair_suggestions
      WHERE job_id=? AND document_id=? AND rule_id=? AND finding_id=?
        AND context_sha256=? AND model=? AND model_version=? AND prompt_version=?`,
    [request.source.job_id, request.source.document_id, request.rule.rule_id, request.finding.finding_id,
      request.context_sha256, model, modelVersion, promptVersion],
  );
  return row ? JSON.parse(row.response_json) : null;
}

async function saveRepairSuggestion(request, response) {
  response = { ...response, provenance: { ...response.provenance, source_identity_sha256: request.source_identity_sha256 } };
  await db.run(
    `INSERT INTO repair_suggestions
      (id, source_kind, job_id, document_id, document_sha256, detector_version, rule_id, finding_id,
       context_sha256, status, provider, model, model_version, prompt_version, response_json)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
    [randomUUID(), request.source.kind, request.source.job_id, request.source.document_id,
      request.source.document_sha256, request.source.detector_version, request.rule.rule_id,
      request.finding.finding_id, request.context_sha256, response.status, response.provenance.provider,
      response.provenance.model, response.provenance.model_version, response.provenance.prompt_version,
      JSON.stringify(response)],
  );
  return response;
}

async function listArchiveRepairSuggestions({ jobId, documentId, ruleId, findingId }) {
  const clauses = [];
  const params = [];
  for (const [column, value] of Object.entries({ job_id: jobId, document_id: documentId, rule_id: ruleId, finding_id: findingId })) {
    if (value) { clauses.push(`${column}=?`); params.push(value); }
  }
  const rows = await db.all(
    `SELECT * FROM repair_suggestions${clauses.length ? ` WHERE ${clauses.join(' AND ')}` : ''} ORDER BY created_at DESC`, params,
  );
  return rows.map(({ response_json, ...row }) => ({ ...row, response: JSON.parse(response_json) }));
}

module.exports = {
  getArchiveFinding,
  buildArchiveRepairRequest,
  findRepairSuggestion,
  saveRepairSuggestion,
  listArchiveRepairSuggestions,
};
