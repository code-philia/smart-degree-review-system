const { createHash, randomUUID } = require('crypto');
const fs = require('fs/promises');
const db = require('../database/db_runtime');
const reportRepository = require('./paperLintReportRepository');
const { RULE_TEXT, BASIC_REPAIR_RULE_IDS, appendEvidence, buildPaperLintReportRepairRequest } = require('./legacyRepairAdapter');
const { extractPdfContext } = require('./repairEvidenceService');

function problem(status, message) {
  const error = new Error(message);
  error.status = status;
  return error;
}

function sha256(content) {
  return createHash('sha256').update(content).digest('hex');
}

async function getPaperLintReportFinding({ reportId, userId, ruleId, findingId }) {
  const report = await reportRepository.findPaperLintReportByIdForUser(reportId, userId);
  if (!report) throw problem(404, '未找到该审查报告');
  if (!RULE_TEXT[ruleId]) throw problem(422, '该规则暂不支持 AI 修复建议');
  const ruleRun = report.result?.rule_runs?.find((run) => run.rule_id === ruleId);
  const finding = ruleRun?.findings?.find((item) => item.finding_id === findingId);
  if (!ruleRun || !finding) throw problem(404, '该报告中不存在指定告警');
  return { report, ruleRun, finding };
}

async function buildPaperLintReportRepairRequestBase({ reportId, userId, ruleId, findingId }) {
  const { report, ruleRun, finding } = await getPaperLintReportFinding({ reportId, userId, ruleId, findingId });
  const pdf = await reportRepository.getPaperLintReportPdfFile(reportId, userId);
  if (!pdf) throw problem(404, '未找到该审查报告');
  if (!pdf.path) throw problem(410, '该报告的原始 PDF 已不可用');
  const documentSha256 = sha256(await fs.readFile(pdf.path));
  const request = buildPaperLintReportRepairRequest({ report, ruleRun, finding, documentSha256 });
  return { request, pdf, finding };
}

async function buildPaperLintReportRepairRequestWithPdfContext(values) {
  const { request, pdf, finding } = await buildPaperLintReportRepairRequestBase(values);
  const reportId = values.reportId;
  const page = Number(finding.location?.page_number || finding.location?.bounding_rect?.page_number);
  if (BASIC_REPAIR_RULE_IDS.has(request.rule.rule_id) && (!Number.isSafeInteger(page) || page < 1)) return request;
  const extracted = await extractPdfContext(pdf.path, finding.location);
  if (!extracted.text.trim()) throw problem(422, 'PDF 目标位置未提取到可用文本上下文');
  return appendEvidence(request, {
    evidence_id: `pdf-context-${request.evidence.length + 1}`,
    source_kind: 'pdf_text',
    text: extracted.text,
    page_number: extracted.page_number,
    location: finding.location,
    source_ref: `paper_lint_report:pdf_context:${reportId}#page=${extracted.page_number}`,
  });
}

async function findPaperLintRepairSuggestion(request, { model, modelVersion, promptVersion } = {}) {
  const clauses = ['report_id=?', 'rule_id=?', 'finding_id=?', 'context_sha256=?'];
  const params = [request.source.report_id, request.rule.rule_id, request.finding.finding_id, request.context_sha256];
  if (model && modelVersion && promptVersion) {
    clauses.push('model=?', 'model_version=?', 'prompt_version=?');
    params.push(model, modelVersion, promptVersion);
  }
  const row = await db.get(
    `SELECT response_json FROM paper_lint_repair_suggestions WHERE ${clauses.join(' AND ')}
     ORDER BY generation DESC, created_at DESC LIMIT 1`,
    params,
  );
  return row ? JSON.parse(row.response_json) : null;
}

async function findLatestPaperLintRepairSuggestion({ reportId, userId, ruleId, findingId, identity, sourceIdentity }) {
  const row = await db.get(
    `SELECT response_json FROM paper_lint_repair_suggestions
     WHERE report_id=? AND user_id=? AND rule_id=? AND finding_id=?
     ORDER BY generation DESC, created_at DESC LIMIT 1`,
    [reportId, userId, ruleId, findingId],
  );
  const response = row ? JSON.parse(row.response_json) : null;
  if (response && identity && (response.provenance.model !== identity.model ||
      response.provenance.model_version !== identity.modelVersion ||
      response.provenance.prompt_version !== identity.promptVersion ||
      response.provenance.source_identity_sha256 !== sourceIdentity)) return null;
  return response;
}

async function savePaperLintRepairSuggestion(request, userId, response) {
  response = { ...response, provenance: { ...response.provenance, source_identity_sha256: request.source_identity_sha256 } };
  await db.withTransaction(async (tx) => {
    const existing = await tx.get(
      `SELECT COALESCE(MAX(generation), 0) AS generation FROM paper_lint_repair_suggestions
       WHERE report_id=? AND rule_id=? AND finding_id=?`,
      [request.source.report_id, request.rule.rule_id, request.finding.finding_id],
    );
    await tx.run(
      `INSERT INTO paper_lint_repair_suggestions
        (id, report_id, user_id, document_sha256, rule_id, finding_id, context_sha256, generation,
         status, provider, model, model_version, prompt_version, response_json)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)`,
      [randomUUID(), request.source.report_id, userId, request.source.document_sha256,
        request.rule.rule_id, request.finding.finding_id, request.context_sha256, existing.generation + 1,
        response.status, response.provenance.provider, response.provenance.model,
        response.provenance.model_version, response.provenance.prompt_version, JSON.stringify(response)],
    );
  });
  return response;
}

module.exports = {
  getPaperLintReportFinding,
  buildPaperLintReportRepairRequestBase,
  buildPaperLintReportRepairRequestWithPdfContext,
  findPaperLintRepairSuggestion,
  findLatestPaperLintRepairSuggestion,
  savePaperLintRepairSuggestion,
};
