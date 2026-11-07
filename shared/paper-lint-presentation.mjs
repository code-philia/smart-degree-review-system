const numericRule = 'abstract_numeric_consistency_check';
const referenceRules = new Set(['sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33']);
const array = value => Array.isArray(value) ? value : [];

export function referenceInfoFindings(run) {
  const findings = array(run.findings).filter(f => !f.prompt_only || ['supported_suspicion', 'insufficient_evidence'].includes(f.reference_review));
  const keys = new Set(findings.map(f => f.finding_id));
  const notices = array(run.compiler_diagnostics).filter(d => d.status === 'UNKNOWN').map((d, index) => ({
    finding_id: `reference-info-${d.node_id || 'entry'}-${d.check_id}-${index}`,
    rule_id: 'sjtu_rule_32', severity: 'info', prompt_only: true, reference_review: 'insufficient_evidence',
    message: '引用核验证据不足，请人工核查。',
    suggestion: '请核对参考文献的题名、作者、年份和 DOI；未检索到充分证据不表示文献不存在。',
    location: d.location || null, evidence: array(d.evidence), basis_details: d.basis_details,
  })).filter(f => !keys.has(f.finding_id));
  return [...findings, ...notices].map(f => ({ ...f, severity: 'info', reference_review: f.reference_review || 'supported_suspicion' }));
}

export function referenceResourcesUnavailable(run) {
  return run.rule_id === 'sjtu_rule_32' && (run.params?.reference_resources_unavailable === true
    || Number(run.params?.reference_verification?.unavailable) > 0 || /检索资源暂不可用/.test(run.message || ''));
}

export function isGenericExecutionWarning(run) {
  if (run.rule_id === numericRule) return false;
  const unavailable = referenceResourcesUnavailable(run);
  if (run.rule_id === 'sjtu_rule_32' && run.execution_status === 'completed' && !unavailable) return false;
  if (referenceRules.has(run.rule_id) && run.execution_status === 'completed'
      && run.publication_status === 'NO_ALERT' && !unavailable) return false;
  return run.execution_status === 'unsupported' || run.execution_status === 'error'
    || run.outcome === 'inconclusive' || unavailable;
}

export function chapterPrerequisiteSuggestion(run) {
  const reason = String(run.message || '');
  // The rule's target can mention both abstracts even when only one is absent.
  const prerequisite = reason.split(/[，,。；;]/, 1)[0];
  const names = ['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'];
  let sections = array(run.params?.core_structure_sections).filter(name => names.includes(name));
  const label = name => name === '英文摘要' ? '英文摘要（Abstract）'
    : name === '摘要' ? /中文摘要|中英文摘要/.test(prerequisite) ? '中文摘要' : /英文摘要/.test(prerequisite) ? '英文摘要（Abstract）' : '摘要' : name;
  if (!sections.length) {
    // Older saved reports predate structured prerequisite metadata. Only infer
    // an absent/incomplete chapter, never a search-service or API failure.
    if (/API|密钥|额度|限流|超时|网络|服务.*(?:不可用|失败)/i.test(reason)) return null;
    sections = names.filter(name => {
      const pattern = (name === '摘要' ? '(?:中文|英文|中英文)?摘要' : name)
        + (name.endsWith('摘要') ? '(?:[（(]Abstract[）)])?' : '');
      return new RegExp(`(?:缺少|缺失|未(?:能|可靠)?识别到?|无法识别)[^，。；]{0,8}${pattern}|${pattern}[^，。；]{0,8}不完整`, 'i').test(prerequisite);
    });
    if (sections.includes('摘要') && sections.includes('英文摘要') && !/中文摘要|中英文摘要/.test(prerequisite)) {
      sections = sections.filter(name => name !== '摘要');
    }
  }
  const labels = [...new Set(sections.map(label))];
  if (!labels.length) return null;
  return `请${/不完整/.test(prerequisite) ? '补全' : '补齐'}或核对${labels.join('、')}，确认内容完整且可读取后重新检测。`;
}

function numericWarningCount(run) {
  const params = run.params || {};
  return array(params.preconditions).filter(condition => condition.passed === false && condition.status !== 'skipped').length
    + Number(Boolean(run.execution_status === 'error' || params.failure || array(params.validation_errors).length));
}

function visibleFindings(run) {
  const findings = array(run.findings);
  if (run.rule_id === 'sjtu_rule_32') return referenceInfoFindings(run);
  if (run.rule_id !== numericRule) return findings;
  const params = run.params || {};
  if (array(params.preconditions).some(condition => condition.passed === false)) return [];
  if (!Array.isArray(params.numeric_results)) return findings;
  return params.numeric_results.filter(row => ['inconsistent', 'inconclusive'].includes(row.status)
    && !array(params.validation_errors).some(error => error.declaration_id === row.declaration_id)
    && !/^结果校验未通过|.*核验执行失败/.test(String(row.reason || '')))
    .map(row => ({ severity: row.status === 'inconsistent' ? 'warning' : 'info' }));
}

/** Display counts are derived from runs, never added to an already transformed summary. */
export function displayedReportSummary(result) {
  const runs = array(result.rule_runs), base = result.summary || {};
  const severity = { error: 0, warning: 0, info: 0 }, issues = new Set();
  let warningCount = 0, findingCount = 0;
  for (const run of runs) {
    const findings = visibleFindings(run);
    findingCount += findings.length;
    if (findings.length) issues.add(run.rule_id);
    for (const finding of findings) {
      const level = finding.severity || run.severity;
      if (level in severity) severity[level]++;
    }
    const count = run.rule_id === numericRule ? numericWarningCount(run) : Number(isGenericExecutionWarning(run));
    warningCount += count;
    if (count) issues.add(run.rule_id);
  }
  return { ...base,
    rule_count: base.rule_count ?? runs.length,
    completed_rule_count: base.completed_rule_count ?? runs.filter(run => run.execution_status === 'completed').length,
    unsupported_rule_count: base.unsupported_rule_count ?? runs.filter(run => run.execution_status === 'unsupported').length,
    error_rule_count: base.error_rule_count ?? runs.filter(run => run.execution_status === 'error').length,
    derived_rule_count: base.derived_rule_count ?? runs.filter(run => run.evidence_mode === 'derived').length,
    finding_count: findingCount + warningCount,
    execution_warning_count: warningCount, error_finding_count: severity.error,
    warning_finding_count: severity.warning, info_finding_count: severity.info, issue_rule_count: issues.size,
  };
}
