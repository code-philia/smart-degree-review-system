const crypto = require('crypto');
const path = require('path');
const { runPaperLintProcess } = require('./paperLintProcess');
const { summarizeRuleRuns } = require('./localFiveRulePaperLintService');

const DOCUMENT_CHECK_ID = 'document_type_check';
const VERSION = 'paper-admission/2.0';
const SCRIPT = path.resolve(__dirname, '../../scripts/check_paper_document.py');
const REQUIRED_SECTIONS = {
  'chinese-thesis': ['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'],
  'english-thesis': ['摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'],
  'research-article': ['摘要', '引言', '主体', '结论', '参考文献'],
};

async function assessPaperDocument(pdfPath, pdfBuffer, { python, signal } = {}) {
  try {
    const { stdout } = await runPaperLintProcess(python, [SCRIPT, pdfPath], {
      signal, timeoutMs: 30000, maxBytes: 64 * 1024,
      env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
    });
    const result = JSON.parse(stdout);
    const digest = crypto.createHash('sha256').update(pdfBuffer).digest('hex');
    const required = REQUIRED_SECTIONS[result?.structure?.profile];
    const completeProof = result?.status === 'accepted'
      && result.reason_code === 'paper_structure_confirmed' && result.compiled === true
      && result.stage === 'complete' && result.structure?.status === 'accepted'
      && Array.isArray(result.structure?.missing_sections) && result.structure.missing_sections.length === 0;
    const partialProof = result?.status === 'accepted'
      && result.reason_code === 'paper_structure_incomplete' && result.compiled === true
      && result.stage === 'partial' && result.structure?.status === 'rejected'
      && Array.isArray(result.structure?.missing_sections) && result.structure.missing_sections.length > 0;
    if (!result || result.version !== VERSION || result.sha256 !== digest
      || !['accepted', 'rejected'].includes(result.status)
      || typeof result.reason !== 'string' || !result.reason.trim()
      || (result.status === 'accepted' && (!completeProof && !partialProof
        || !['accepted', 'rejected'].includes(result.structure?.status)
        || !['chinese-thesis', 'english-thesis', 'research-article'].includes(result.structure?.profile)
        || !required || !Array.isArray(result.structure?.required_sections)
        || result.structure.required_sections.length !== required.length
        || !required.every(name => result.structure.required_sections.includes(name))
        || !Array.isArray(result.structure?.missing_sections)
        || (completeProof && !result.structure.required_sections.every(name => result.structure.observed_sections?.[name] === true))))) {
      throw new Error('Invalid document admission proof');
    }
    return result;
  } catch (error) {
    if (signal?.aborted) throw error;
    // Fail closed: classifier crashes, timeouts and malformed output never admit a PDF.
    return { version: VERSION, status: 'rejected', reason_code: 'validation_unavailable',
      reason: '论文身份校验未完成，请稍后重试；本次未解析 Paper Model，也未执行任何论文规则。' };
  }
}

function documentRejectionResult(assessment, selectedRuleIds) {
  const confirmed = assessment.reason_code === 'non_paper_identity';
  const structureError = assessment.reason_code === 'paper_structure_incomplete';
  const compilationError = ['paper_model_compile_failed', 'validation_unavailable'].includes(assessment.reason_code);
  const message = structureError
    ? '论文核心章节不完整，Paper Model 编译失败。所有论文规则均未检测。'
    : compilationError ? 'Paper Model 编译校验未完成，所有论文规则均未检测。'
    : confirmed
    ? '上传的 PDF 不是论文，不能被 Paper Model 解析编译。所有论文规则均未检测。'
    : '无法确认上传的 PDF 是论文，不能被 Paper Model 解析编译。所有论文规则均未检测。';
  const run = { rule_id: DOCUMENT_CHECK_ID, rule_run_id: 'document_admission', severity: 'error',
    execution_status: 'completed', evidence_mode: 'native', outcome: 'issues_found',
    message, findings: [{ finding_id: 'document_not_paper', rule_id: DOCUMENT_CHECK_ID,
      severity: 'error', message: message + ' ' + assessment.reason,
      suggestion: '请上传论文正文 PDF；推荐表、申请材料、说明文档等不能作为论文检测。' }] };
  return { type: 'paper_lint', paper_title: '上传文档的 Paper Model 编译失败',
    ruleset: { id: 'paper-document-admission', name: '论文编译校验', version_number: 2, version_label: VERSION },
    document_validation: { ...assessment, skipped_rule_ids: [...selectedRuleIds] },
    rule_runs: [run], summary: { ...summarizeRuleRuns([run]), rule_count: 0, completed_rule_count: 0,
      issue_rule_count: 0, derived_rule_count: 0 } };
}

module.exports = { assessPaperDocument, documentRejectionResult, DOCUMENT_CHECK_ID };
