const crypto = require('crypto');
const basicRules = require('../../../shared/basic-repair-rules.json');
const BASIC_REPAIR_RULE_IDS = new Set(basicRules.map(rule => rule.rule_id));
const basicRuleText = Object.fromEntries(basicRules.map(rule => [rule.rule_id, `${rule.title}：${rule.description} 以告警及规则参数中的具体要求为准，不补造研究内容或事实；检测器记录不等于 PDF 原文，缺少核验上下文时使用 insufficient_context 并说明需要核对什么。`]));

const RULE_TEXT = Object.freeze({
  ...basicRuleText,
  required_section_completeness_check: '核心章节完整性：按 GB/T 7713.1—2025 附录 A 表 A.1 检查题名页、原创性声明、使用授权说明、摘要及关键词、目录、引言、主体、结论、参考文献。根据告警中具体缺失项提出补齐建议。告警是全文检查的缺失记录，没有可引用的缺失原句或精确修改页；不得将封面题名当作错误原文，不得编造研究内容、签名或日期。',
  chinese_english_symbol_mix_check: '本地检测已确认中文文字之间出现英文半角标点。根据提供的原文，明确将该处半角逗号、分号、冒号、问号或叹号改为对应中文全角标点；保持其余文字和正常英文、公式、代码及网址不变。',
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
  sjtu_rule_31: '文内引注与文后参考文献格式应符合适用的 GB/T 7714 规定。仅对原文和规范已证实的类型标识、著录字段、标点或引注体例问题提出修改，按资源类型区分必备与有则必备；不将正常换行或跨行断词当作错误，类型或版本不明时先核对，不编造作者、题名、日期、DOI 或其他元数据。',
  sjtu_rule_32: '被引文献的身份与存在性应有可核验依据。公开检索查不到不能据此证明文献不存在，也不同于正文引用编号没有对应本地文献条目。依据已有来源核对文献身份、题名和标识符，证实引用错误后再建议更正、删除或替换，并同步文内引注；不得编造替代文献或 DOI。完整受控文献库的排除证明仅能说明该库限定范围内不存在，不得外推到现实世界；公开检索或受控库证据不完整时使用 insufficient_context，不把检索缺失当作不存在。',
  sjtu_rule_33: '具体引用语境中的论述应与被引文献实际内容相关并具有对应的支撑关系。结合引用句、被引条目和已提供的内容证据，建议收敛论断、调整引用位置或由作者补充确有支持的来源；不得仅凭题名或关键词差异判断不相关，不得编造文献内容、替代来源或研究事实。缺少内容证据时使用 insufficient_context，证据反驳原告警时使用 evidence_conflict。',
});

const CITATION_REPAIR_RULE_IDS = new Set(['sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33']);
const ruleVersion = (id) => CITATION_REPAIR_RULE_IDS.has(id) ? 'citation-repair-20261020' : BASIC_REPAIR_RULE_IDS.has(id) ? 'basic-repair-20261020' : 'legacy-rule-text-20261018';

// Keep the compiler's cited-content evidence and all supplied normative excerpts.
// Group normative text so unrelated clauses cannot exhaust the eight evidence slots.
function citationEvidence(finding) {
  const items = [];
  const normative = [];
  const original = String(finding.location?.text_excerpt || '').trim();
  for (const [index, entry] of (Array.isArray(finding.evidence) ? finding.evidence : []).entries()) {
    if (!entry || typeof entry !== 'object') continue;
    const quote = typeof entry.quote === 'string' ? entry.quote.trim() : '';
    const url = typeof entry.url === 'string' ? entry.url : '';
    if (entry.kind === 'normative_span') { if (quote) normative.push(quote); continue; }
    const provenance = {};
    for (const key of ['source_id', 'origin', 'source_sha256', 'node_id', 'content_id', 'work_id', 'start', 'end']) {
      if (entry[key] !== undefined) provenance[key] = entry[key];
    }
    let scope = '';
    if (entry.kind === 'controlled_catalog_scope') {
      scope = '受控文献库排除证据（仅限该受控文献库，不能证明现实世界不存在）：' + JSON.stringify({
        domain: entry.domain, complete: entry.complete, search_scope: entry.search_scope,
        query: entry.query, catalog_size: entry.catalog_size, protocol: entry.protocol,
      });
    }
    if (!quote && !url && !scope) continue;
    if (entry.kind === 'source_span' && quote === original && !url) continue;
    items.push({ evidence_id: `compiler-evidence-${index + 1}`,
      source_kind: entry.kind === 'source_span' ? 'pdf_text' : 'retrieval',
      text: [quote, scope, Object.keys(provenance).length ? '来源标识：' + JSON.stringify(provenance) : '', url ? `来源链接：${url}` : ''].filter(Boolean).join('\n'),
      source_ref: ['paper_compiler', entry.kind || 'evidence', entry.id || String(index), entry.provider || '', url, entry.proof_sha256 || ''].join(':'),
    });
  }
  if (normative.length) items.push({ evidence_id: 'compiler-normative', source_kind: 'retrieval',
    text: '原告警提供的规范依据（不是被引文献内容）：\n' + [...new Set(normative)].join('\n'),
    source_ref: 'paper_compiler:normative' });
  return items;
}

function sha256(value) {
  return crypto.createHash('sha256').update(value).digest('hex');
}

function contextSha256(ruleId, finding, evidence, source) {
  return sha256(JSON.stringify({
    rule_id: ruleId, rule_text: RULE_TEXT[ruleId], rule_version: ruleVersion(ruleId), source,
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
    ...(CITATION_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? citationEvidence(finding) : []),
    ...(Array.isArray(finding.anchors) ? finding.anchors.map((anchor, index) => evidenceFromAnchor(anchor, index + 1)) : []),
  ].filter(Boolean);
  if (BASIC_REPAIR_RULE_IDS.has(ruleRun.rule_id) && !finding.location?.text_excerpt) {
    evidence[0] = {...evidence[0], source_kind:'retrieval', text:'检测器记录（不是 PDF 原文）：' + (finding.message || ''), source_ref:'recorded_finding:' + finding.finding_id};
  }
  const request = {
    schema_version: 'repair-request-v1',
    source: {
      kind: 'legacy_archive',
      ...(BASIC_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? {rule_parameters_sha256:sha256(JSON.stringify(ruleRun.params || null))} : {}),
      job_id: job.id,
      document_id: document.id,
      document_sha256: provenance.pdf_sha || sha256(`${job.id}:${document.id}:${document.relative_path || ''}`),
      detector_version: provenance.detector_version_sha || (CITATION_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? ruleRun.package_sha256 || ruleRun.pipeline_version || null : null),
      ...(CITATION_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? { package_sha256: ruleRun.package_sha256 || null, pipeline_version: ruleRun.pipeline_version || null, runtime_version: ruleRun.runtime_version || null } : {}),
    },
    rule: { rule_id: ruleRun.rule_id, text: ruleText, version: ruleVersion(ruleRun.rule_id), ...(BASIC_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? {parameters:ruleRun.params || null} : {}) },
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
    ...(CITATION_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? citationEvidence(finding) : []),
    ...(Array.isArray(finding.anchors) ? finding.anchors.map((anchor, index) => evidenceFromAnchor(anchor, index + 1)) : []),
  ].filter(Boolean).map((item) => ({ ...item, source_ref: item.source_ref.replace('legacy_archive:', 'paper_lint_report:') }));
  if (BASIC_REPAIR_RULE_IDS.has(ruleRun.rule_id) && !finding.location?.text_excerpt) {
    evidence[0] = {...evidence[0], source_kind:'retrieval', text:'检测器记录（不是 PDF 原文）：' + (finding.message || ''), source_ref:'recorded_finding:' + finding.finding_id};
  }
  const request = {
    schema_version: 'repair-request-v1',
    source: {
      kind: 'paper_lint_report',
      ...(BASIC_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? {rule_parameters_sha256:sha256(JSON.stringify(ruleRun.params || null))} : {}),
      report_id: report.id,
      document_sha256: documentSha256,
      detector_version: report.result?.execution_provenance?.detector_version_sha || (CITATION_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? ruleRun.package_sha256 || ruleRun.pipeline_version || null : null),
      ...(CITATION_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? { package_sha256: ruleRun.package_sha256 || null, pipeline_version: ruleRun.pipeline_version || null, runtime_version: ruleRun.runtime_version || null } : {}),
    },
    rule: { rule_id: ruleRun.rule_id, text: ruleText, version: ruleVersion(ruleRun.rule_id), ...(BASIC_REPAIR_RULE_IDS.has(ruleRun.rule_id) ? {parameters:ruleRun.params || null} : {}) },
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
  BASIC_REPAIR_RULE_IDS,
  RULE_TEXT,
  appendEvidence,
  buildLegacyRepairRequest,
  buildPaperLintReportRepairRequest,
  evidenceFromFinding,
  evidenceFromAnchor,
  sha256,
};
