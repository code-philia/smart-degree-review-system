const crypto = require('crypto');

const RULE_TEXT = Object.freeze({
  sjtu_rule_11: '正文引用的图不存在。',
  sjtu_rule_13: '图题缺失。',
  sjtu_rule_14: '表题缺失。',
  sjtu_rule_15: '出现未被引用的图。',
  sjtu_rule_16: '出现未被引用的表。',
  sjtu_rule_18: '正文公式引用目标缺失。',
  sjtu_rule_22: '正文引文没有对应参考文献条目。',
  sjtu_rule_24: '参考文献列表中存在未被正文引用的条目。',
  sjtu_rule_28: '目录中的核心内容页码系统性错位。',
  sjtu_rule_29: '正文引用的本论文附录目标完全缺失。',
});

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function contextSha256(ruleId, finding, evidence, source) {
  return sha256(JSON.stringify({
    rule_id: ruleId, rule_text: RULE_TEXT[ruleId], rule_version: 'legacy-rule-text-20261018', source,
    location: finding.location, anchors: finding.anchors,
    finding_id: finding.finding_id,
    message: finding.message,
    evidence: evidence.map(({ evidence_id, source_kind, text, page_number, source_ref }) =>
      ({ evidence_id, source_kind, text, page_number, source_ref })),
  }));
}

function evidenceId(index) {
  return `legacy-evidence-${index + 1}`;
}

function evidenceFromFinding(finding, index = 0) {
  const location = finding.location || {};
  const text = String(location.text_excerpt || finding.message || '').trim();
  return {
    evidence_id: evidenceId(index),
    source_kind: 'pdf_text',
    text,
    page_number: location.page_number || location.bounding_rect?.page_number,
    location: location || undefined,
    source_ref: 'legacy_archive:finding_location',
  };
}

function evidenceFromAnchor(anchor, index) {
  const location = anchor?.location || {};
  const text = String(anchor?.text || location.text_excerpt || anchor?.message || '').trim();
  if (!text) return null;
  return {
    evidence_id: evidenceId(index),
    source_kind: 'retrieval',
    text,
    page_number: location.page_number || location.bounding_rect?.page_number,
    location: location || undefined,
    source_ref: 'legacy_archive:finding_anchor',
  };
}

function buildLegacyRepairRequest({ job, document, ruleRun, finding }) {
  if (!job?.id || !document?.id || !ruleRun?.rule_id || !finding?.finding_id) {
    throw new TypeError('历史告警缺少构建修复建议所需的关联标识');
  }
  const ruleText = RULE_TEXT[ruleRun.rule_id];
  if (!ruleText) {
    throw Object.assign(new Error(`未支持的修复建议规则：${ruleRun.rule_id}`), { status: 422 });
  }
  const provenance = document.result?.execution_provenance || {};
  const evidence = [
    evidenceFromFinding(finding),
    ...(Array.isArray(finding.anchors) ? finding.anchors.map((anchor, index) => evidenceFromAnchor(anchor, index + 1)) : []),
  ].filter(Boolean);
  const request = {
    schema_version: 'repair-request-v1',
    source: {
      kind: 'legacy_archive',
      job_id: job.id,
      document_id: document.id,
      document_sha256: provenance.pdf_sha || sha256(`${job.id}:${document.id}:${document.relative_path || ''}`),
      detector_version: provenance.detector_version_sha || null,
    },
    rule: { rule_id: ruleRun.rule_id, text: ruleText, version: 'legacy-rule-text-20261018' },
    finding: {
      finding_id: finding.finding_id,
      message: finding.message || '',
      location: finding.location,
      anchors: Array.isArray(finding.anchors) ? finding.anchors : [],
    },
    evidence,
  };
  request.context_sha256 = contextSha256(ruleRun.rule_id, finding, evidence, request.source);
  request.source_identity_sha256 = request.context_sha256;
  return request;
}

function buildPaperLintReportRepairRequest({ report, ruleRun, finding, documentSha256 }) {
  if (!report?.id || !report?.result || !ruleRun?.rule_id || !finding?.finding_id || !documentSha256) {
    throw new TypeError('单篇报告告警缺少构建修复建议所需的关联标识');
  }
  const ruleText = RULE_TEXT[ruleRun.rule_id];
  if (!ruleText) {
    throw Object.assign(new Error(`未支持的修复建议规则：${ruleRun.rule_id}`), { status: 422 });
  }
  const evidence = [
    evidenceFromFinding(finding),
    ...(Array.isArray(finding.anchors) ? finding.anchors.map((anchor, index) => evidenceFromAnchor(anchor, index + 1)) : []),
  ].filter(Boolean).map((item) => ({ ...item, source_ref: item.source_ref.replace('legacy_archive:', 'paper_lint_report:') }));
  const request = {
    schema_version: 'repair-request-v1',
    source: {
      kind: 'paper_lint_report',
      report_id: report.id,
      document_sha256: documentSha256,
      detector_version: report.result?.execution_provenance?.detector_version_sha || null,
    },
    rule: { rule_id: ruleRun.rule_id, text: ruleText, version: 'legacy-rule-text-20261018' },
    finding: {
      finding_id: finding.finding_id,
      message: finding.message || '',
      location: finding.location,
      anchors: Array.isArray(finding.anchors) ? finding.anchors : [],
    },
    evidence,
  };
  request.context_sha256 = contextSha256(ruleRun.rule_id, finding, evidence, request.source);
  request.source_identity_sha256 = request.context_sha256;
  return request;
}

function appendEvidence(request, nextEvidence) {
  const evidence = [...request.evidence, nextEvidence];
  return {
    ...request,
    evidence,
    context_sha256: contextSha256(request.rule.rule_id, request.finding, evidence, request.source),
  };
}

module.exports = {
  RULE_TEXT,
  appendEvidence,
  buildLegacyRepairRequest,
  buildPaperLintReportRepairRequest,
  evidenceFromFinding,
  evidenceFromAnchor,
  sha256,
};
