const { summarizeRuleRuns } = require('./localFiveRulePaperLintService');

const CORE_RULE_ID = 'required_section_completeness_check';
function sectionName(name, profile) {
  if (name === '英文摘要' || name === '摘要' && profile === 'english-thesis') return '英文摘要（Abstract）';
  return name === '摘要' && profile === 'chinese-thesis' ? '中文摘要' : name;
}

function coreStructureRun(admission) {
  if (admission.status !== 'accepted' || admission.stage !== 'partial') return null;
  const structure = admission.structure;
  const findings = [
    ...structure.missing_sections.map(name => ({ name,
      message: `缺少${sectionName(name, structure.profile)}：未在论文正文中识别到该章节。` })),
    ...structure.incomplete_sections.map(name => ({ name,
      message: `${sectionName(name, structure.profile)}不完整：${(structure.abstract_sections?.[name]?.issues || ['未识别到完整章节内容']).join('；')}。` })),
  ].map(({ name, message }) => ({ finding_id: `mandatory_core_${name}`, rule_id: CORE_RULE_ID,
    severity: 'warning', message, suggestion: `请补齐或核对${sectionName(name, structure.profile)}。`, location: null, anchors: [] }));
  if (!findings.length) return null;
  return { rule_id: CORE_RULE_ID, rule_run_id: 'mandatory_core_structure', severity: 'warning',
    params: { automatic_core_check: true }, execution_status: 'completed', evidence_mode: 'native',
    outcome: 'issues_found', message: '核心章节结构由系统自动检查，不受前端勾选影响。', findings };
}

function mergeCoreRuns(first, second) {
  if (!first) return second;
  if (!second) return first;
  const selected = first.params?.automatic_core_check && !second.params?.automatic_core_check ? second : first;
  const automatic = selected === first ? second : first;
  const findings = [...selected.findings];
  for (const finding of automatic.findings) {
    // A selected native check may provide a better PDF location for the same
    // section. Keep it instead of duplicating the background finding.
    const title = finding.message.split('：')[0];
    if (!findings.some(item => item.message?.split('：')[0] === title)) findings.push(finding);
  }
  return { ...selected, params: { ...selected.params, automatic_core_check: true }, findings,
    outcome: findings.length ? 'issues_found' : selected.outcome };
}

function attachCoreStructure(result, admission) {
  const automatic = coreStructureRun(admission);
  if (!automatic) return { ...result, document_validation: admission };
  const runs = [...result.rule_runs];
  const index = runs.findIndex(run => run.rule_id === CORE_RULE_ID);
  if (index < 0) runs.push(automatic); else runs[index] = mergeCoreRuns(runs[index], automatic);
  return { ...result, document_validation: admission, rule_runs: runs, summary: summarizeRuleRuns(runs) };
}

function unavailableRuleRuns(admission, selectedRuleIds) {
  if (admission.status !== 'accepted') return [];
  const s = admission.structure;
  const issue = name => s.missing_sections.includes(name) ? `缺少${sectionName(name, s.profile)}`
    : s.incomplete_sections.includes(name) ? `${sectionName(name, s.profile)}不完整` : null;
  const keywordIssue = issue('摘要') || (s.abstract_sections?.['摘要']?.has_keywords === false
    || s.missing_sections.includes('关键词') ? `未识别到${sectionName('摘要', s.profile)}中的非空关键词` : null);
  const abstracts = ['摘要', ...(s.profile === 'chinese-thesis' ? ['英文摘要'] : [])];
  const pairIssue = abstracts.map(issue).find(Boolean);
  const keywordsIssue = pairIssue || abstracts.map(name => s.abstract_sections?.[name]?.has_keywords === false
    ? `未识别到${sectionName(name, s.profile)}中的非空关键词` : null).find(Boolean);
  const requirements = {
    sjtu_rule_18: [issue('主体'), '正文公式引用'],
    sjtu_rule_22: [issue('参考文献') || issue('主体'), '正文引文编号'],
    sjtu_rule_24: [issue('参考文献') || issue('主体'), '参考文献引用情况'],
    sjtu_rule_28: [issue('目录') || issue('主体'), '目录页码'],
    sjtu_rule_31: [issue('参考文献'), '引用格式'],
    sjtu_rule_32: [issue('参考文献'), '外部文献存在性'],
    sjtu_rule_33: [issue('参考文献'), '引用文献完整性'],
    keyword_count_check: [keywordIssue, '该摘要的关键词数量'],
    abstract_object_number_check: [pairIssue, '完整摘要中的图表公式文献编号'],
    bilingual_abstract_consistency_check: [pairIssue, '中英文摘要内容一致性'],
    bilingual_keywords_correspondence_check: [keywordsIssue, '中英文关键词语义对应'],
    abstract_numeric_consistency_check: [issue('摘要') || issue('主体'), '摘要数值声明与正文实验结果一致性'],
    typo_detection_check: [issue('主体'), '正文错别字'],
    chapter_new_page_check: [issue('主体'), '章标题另起页'],
  };
  return selectedRuleIds.flatMap(rule_id => {
    const [reason, target] = requirements[rule_id] || [];
    const message = `未能检测：${reason}，无法可靠检查${target}。`;
    return reason ? [{ rule_id, rule_run_id: `unavailable_${rule_id}`, severity: 'info',
      execution_status: 'unsupported', evidence_mode: 'unsupported', outcome: 'inconclusive', findings: [],
      ...(rule_id === 'abstract_numeric_consistency_check' ? { params: { preconditions: [{
        id: 'core_structure', passed: false, status: 'failed', reason: message,
        suggestion: '请补齐或核对摘要和正文的核心章节后重新检测。',
      }] } } : {}), message }] : [];
  });
}

module.exports = { CORE_RULE_ID, coreStructureRun, mergeCoreRuns, attachCoreStructure, unavailableRuleRuns };
