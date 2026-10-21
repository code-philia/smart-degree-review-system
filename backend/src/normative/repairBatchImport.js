const { isDeepStrictEqual } = require('util');
const { sha256 } = require('./legacyRepairAdapter');
const { buildMessages, validateModelAnswer, PROMPT_VERSION } = require('./repairModelProposalService');

function requireEqual(actual, expected, label) {
  if (!isDeepStrictEqual(actual, expected)) throw new Error('Imported repair changed: ' + label);
}
function comparableMessages(messages) {
  if (!Array.isArray(messages) || messages.length !== 2) throw new Error('Imported repair changed: model prompt');
  let user;
  try { user = JSON.parse(messages[1].content); } catch { throw new Error('Imported repair changed: model prompt'); }
  if (!Array.isArray(user?.evidence)) throw new Error('Imported repair changed: model prompt');
  // The original batch puts finding evidence before PDF context. Only ordering
  // may differ; every displayed field and the system instruction remain exact.
  return [messages[0], {...messages[1], content:{...user,
    evidence:[...user.evidence].sort((a,b) => String(a.evidence_id).localeCompare(String(b.evidence_id))),
  }}];
}
function originalContextHash(request) {
  return sha256(JSON.stringify({
    rule_id: request.rule.rule_id,
    finding_id: request.finding.finding_id,
    message: request.finding.message,
    evidence: request.evidence.map(({ evidence_id, source_kind, text, page_number, source_ref }) =>
      ({ evidence_id, source_kind, text, page_number, source_ref })),
  }));
}
function verifyBatchRepairRecord(record, current, { document, pdfSha256, batchSha256, inputName, model, modelVersion }) {
  if (record?.request?.schema_version !== 'repair-request-v1' || record?.response?.schema_version !== 'repair-response-v2' ||
      current?.source?.kind !== 'legacy_archive') throw new Error('Unsupported imported repair schema');
  const expectedIds = {jobId:current.source.job_id, documentId:current.source.document_id,
    ruleId:current.rule.rule_id, findingId:current.finding.finding_id};
  requireEqual(record.source, expectedIds, 'finding identity');
  requireEqual(record.relative_path, document.relative_path, 'PDF path');
  for (const key of ['source', 'rule', 'finding', 'evidence']) requireEqual(record.request[key], current[key], key);
  if (!/^[a-f0-9]{64}$/.test(pdfSha256 || '') || !/^[a-f0-9]{64}$/.test(batchSha256 || '')) throw new Error('Missing PDF/batch SHA-256');
  const detectorPdfHash = document.result?.execution_provenance?.pdf_sha;
  const fallbackHash = sha256(current.source.job_id + ':' + current.source.document_id + ':' + document.relative_path);
  if (detectorPdfHash) {
    requireEqual(pdfSha256, detectorPdfHash, 'PDF content hash');
    requireEqual(current.source.document_sha256, pdfSha256, 'PDF source hash');
  } else if (current.source.document_sha256 !== pdfSha256 && current.source.document_sha256 !== fallbackHash) {
    throw new Error('Unverified legacy PDF identity');
  }
  const original = originalContextHash(record.request);
  requireEqual(record.request.context_sha256, original, 'original request context');
  const response = record.response;
  requireEqual(response.source, record.request.source, 'response source');
  requireEqual(response.rule_id, current.rule.rule_id, 'response rule');
  requireEqual(response.finding_id, current.finding.finding_id, 'response finding');
  requireEqual(response.provenance?.context_sha256, original, 'response context');
  requireEqual(response.provenance?.prompt_version, PROMPT_VERSION, 'prompt version');
  if (model) requireEqual(response.provenance.model, model, 'model');
  if (modelVersion) requireEqual(response.provenance.model_version, modelVersion, 'model version');
  requireEqual(comparableMessages(record.prompt_messages), comparableMessages(buildMessages(current)), 'model prompt');
  const validated = validateModelAnswer(response, current);
  requireEqual(response.status, validated.status, 'response status');
  requireEqual(response.actions, validated.actions, 'response actions');
  // Original generation facts remain intact; these fields document a distinct
  // verification/binding operation rather than pretending the model ran again.
  return {...response, provenance:{...response.provenance,
    source_identity_sha256:current.source_identity_sha256,
    cache_context_sha256:current.context_sha256,
    verified_pdf_sha256:pdfSha256,
    import_batch_sha256:batchSha256,
    imported_from:inputName,
    imported_at:new Date().toISOString(),
  }};
}
module.exports = { verifyBatchRepairRecord };
