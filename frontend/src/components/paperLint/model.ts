import type { PaperLintFinding, PaperLintResult, PaperLintRuleRun } from '../../api/paperLint';
import { numericDisplayFindings as sharedNumericDisplayFindings, displayedReportSummary, executionWarningFeedbackTargets, isGenericExecutionWarning, chapterPrerequisiteSuggestion, referenceResourcesUnavailable, referenceResourceMessage, referenceInfoFindings } from '../../../../shared/paper-lint-presentation.mjs';
export { referenceResourcesUnavailable } from '../../../../shared/paper-lint-presentation.mjs';

export type PaperLintFindingItem = {
  key: string;
  finding: PaperLintFinding;
  ruleRun: PaperLintRuleRun;
  index: number;
};

export type RuleExecutionWarning = {
  feedbackTarget?: PaperLintFindingItem;
  ruleId?: string;
  title: string;
  reason: string;
  suggestion: string;
  preconditionId?: 'abstract_numeric' | 'contribution_mapping' | 'experiment_subsection';
  issueTitle?: string;
  example?: string;
  explanation?: string;
  note?: string;
};
const numericRule = 'abstract_numeric_consistency_check';
export const documentCheckId = 'document_type_check';
export const documentCheckTitle = '论文编译校验';
export function isDocumentBlocked(runs: PaperLintRuleRun[]): boolean {
  return runs.some(run => run.rule_id === documentCheckId);
}
export function referenceReviewMessage(run?: PaperLintRuleRun): string | null {
  if (run?.rule_id !== 'sjtu_rule_32') return null;
  if (run.message && run.message !== '未触发告警') return run.message;
  const diagnostics = run.compiler_diagnostics || [];
  if (!diagnostics.length) return '历史报告未记录完整核验详情，请增量补跑后查看。';
  const quota = diagnostics.filter(row => row.reasons.some(reason => /QUOTA_EXHAUSTED/.test(reason))).length;
  const missing = diagnostics.filter(row => row.reasons.some(reason => /API_KEY.*not configured/.test(reason))).length;
  const unavailable = diagnostics.filter(row => row.reasons.some(reason => /reference_lookup_unavailable|HTTP_[45]\d\d|TimeoutError/.test(reason))).length;
  const unmatched = Math.max(0, diagnostics.length - quota - missing - unavailable);
  return [
    `${diagnostics.length} 条参考文献尚未完成核验。`,
    quota ? `${quota} 条因检索额度不足未完成。` : null,
    missing ? `${missing} 条因检索密钥未配置未完成。` : null,
    unavailable ? `${unavailable} 条因检索服务暂不可用未完成。` : null,
    unmatched ? `${unmatched} 条未匹配到充分的文献身份依据，需人工核查。` : null,
  ].filter(Boolean).join(' ');
}

function warningFeedbackItem(run: PaperLintRuleRun, findingId: string, index: number): PaperLintFindingItem {
  return { key: findingId, ruleRun: run, index,
    finding: { finding_id: findingId, rule_id: run.rule_id, message: run.message || '' } };
}

export function numericExecutionWarnings(run?: PaperLintRuleRun): RuleExecutionWarning[] {
  if (!run || run.rule_id !== numericRule) return [];
  const params = run.params || {};
  const preconditionCopy = {
    abstract_numeric: {
      issueTitle: '摘要中不存在可核验的含有数值的论点',
      example: '“本文提出测试用例增强的需求理解技术 ACECODER，在三个公开评估基准的 Pass@1 指标上取得最高 88.4% 的相对提升。”',
      explanation: '该示例包含明确的研究对象（ACECODER）、评价指标（Pass@1）和数值结果（88.4%），可作为后续一致性核验的候选论点。',
      suggestion: '如果论文摘要中已有相关实验结果，可以补充或明确其评价指标、数值及必要的实验条件，以便系统进行核验。如果摘要本身不涉及数值型实验结论，则无需为了使用本规则而额外添加。',
    },
    contribution_mapping: {
      issueTitle: '摘要论点与研究贡献或正文章节的对应关系不明确',
      example: '摘要中：\n“本文提出测试用例增强的需求理解技术 ACECODER，在三个公开评估基准的 Pass@1 指标上取得最高 88.4% 的相对提升。”\n\n正文目录中：\n“第五章 测试用例增强的需求理解技术”',
      explanation: '摘要中的 Pass@1 性能提升结论对应“测试用例增强的需求理解技术”这一研究贡献，而该研究贡献又能够对应到正文第五章。',
      suggestion: '请检查摘要中数值型论点是否与研究贡献有明确对应，并确保其能够对应到正文或目录中的具体研究章节。章节标题无需与摘要表述完全一致，但应清楚体现相应的研究主题，便于定位相关内容。',
    },
    experiment_subsection: {
      issueTitle: '研究贡献下不存在明确的实验章节',
      example: '摘要中的研究贡献：\n“本文提出测试用例增强的需求理解技术 ACECODER，在三个公开评估基准的 Pass@1 指标上取得最高 88.4% 的相对提升。”\n\n正文目录结构：\n第五章 测试用例增强的需求理解技术\n　5.1 研究问题分析\n　5.4 实验评估\n　　5.4.1 实验设置\n　　5.4.2 实验结果\n　5.5 本章小结',
      explanation: '上述目录在对应研究贡献的章节下设置了明确的实验评估及实验结果子章节，便于系统定位与摘要论点相关的实验性证据。',
      suggestion: '请检查正文目录，确保相关研究贡献具有明确对应的实验评估内容，并在所属章节下设置清晰的实验子章节。章节名称无需与示例完全一致，但应能够根据目录结构定位相应的实验结果。',
      note: '此条检查的是目录与章节结构能否支持实验定位，而不是要求所有论文必须有一个叫“实验评估”的章节。',
    },
  } as const;
  const conditions = Array.isArray(params.preconditions) ? params.preconditions : [];
  const targets = executionWarningFeedbackTargets(run);
  const failed = conditions.filter(c => c.passed === false && c.status !== 'skipped');
  const warnings: RuleExecutionWarning[] = failed.map(c => {
    const copy = preconditionCopy[c.id as keyof typeof preconditionCopy];
    return copy ? {
      title: '论点论据一致性检测',
      reason: String(c.reason || '未满足该前置条件'),
      suggestion: copy.suggestion,
      preconditionId: c.id as keyof typeof preconditionCopy,
      ...copy,
    } : {
      title: '论点论据一致性检测',
      reason: String(c.reason || '未满足该前置条件'),
      suggestion: String(c.suggestion || '请调整论文中的相应摘要、研究贡献或实验章节组织后重新检测。'),
    };
  });
  if (run.execution_status === 'error' || params.failure || (Array.isArray(params.validation_errors) && params.validation_errors.length)) {
    warnings.push({ title: '论点论据一致性检测未完成', reason: '当前系统使用人数较多，API 调用暂时繁忙，部分核验未完成。已完成的有效结果仍予以保留。', suggestion: '请稍后重试；若持续失败，请联系管理员检查运行记录。' });
  }
  return warnings.map((warning, index) => ({ ...warning, ruleId: numericRule,
    feedbackTarget: warningFeedbackItem(run, targets[index].findingId, index) }));
}

const executionRuleTitles: Record<string, string> = {
  sjtu_rule_18: '正文公式引用目标缺失',
  sjtu_rule_22: '正文引文引用编号缺失',
  sjtu_rule_24: '参考文献列表中存在未被正文引用的条目',
  sjtu_rule_28: '目录中的核心内容页码系统性错位',
  sjtu_rule_31: '引用格式错误',
  sjtu_rule_32: '引用的外部文献不存在',
  sjtu_rule_33: '引用文献完整性检查',
  typo_detection_check: '正文错别字检测',
  bilingual_abstract_consistency_check: '中英文摘要内容一致性',
  bilingual_keywords_correspondence_check: '中英文关键词语义对应',
  required_section_completeness_check: '核心章节完整性',
  chinese_english_symbol_mix_check: '中英文标点符号是否混用',
  keyword_count_check: '关键词数量',
  abstract_object_number_check: '摘要图表公式文献编号',
  chapter_new_page_check: '章标题另起一页',
};

/** Converts backend unsupported/error/inconclusive runs into visible UI warnings. */
export function genericExecutionWarnings(runs: PaperLintRuleRun[] = []): RuleExecutionWarning[] {
  return runs
    .filter(isGenericExecutionWarning)
    .map(run => {
      const title = executionRuleTitles[run.rule_id] || run.rule_id;
      const reason = String(referenceResourceMessage(run) || run.message || '本规则因缺少必要的论文结构，暂无法可靠判定。');
      return {
        ruleId: run.rule_id,
        feedbackTarget: warningFeedbackItem(run, executionWarningFeedbackTargets(run)[0].findingId, 0),
        title,
        reason,
        suggestion: chapterPrerequisiteSuggestion(run) || '请稍后重试；如问题持续，请检查运行记录。',
      };
    });
}

/** Feedback targets include visible warnings without turning them into PDF findings. */
export function paperLintFeedbackItems(result: Pick<PaperLintResult, 'rule_runs'>): PaperLintFindingItem[] {
  const warnings = result.rule_runs.flatMap(run => run.rule_id === numericRule ? numericExecutionWarnings(run) : genericExecutionWarnings([run]));
  return [...flattenPaperLintFindings(result), ...warnings.flatMap(warning => warning.feedbackTarget ? [warning.feedbackTarget] : [])];
}

export function numericDisplayFindings(run: PaperLintRuleRun): PaperLintFinding[] {
  return sharedNumericDisplayFindings(run);
}

function pageNumber(item: PaperLintFindingItem) {
  return (
    item.finding.location?.page_number ?? item.finding.anchors?.[0]?.location.page_number ?? Number.MAX_SAFE_INTEGER
  );
}

function topPosition(item: PaperLintFindingItem) {
  const location = item.finding.location;
  return location?.type === 'pdf_bbox' ? location.bounding_rect.y1 : Number.MAX_SAFE_INTEGER;
}

export function comparePaperLintRuleIds(left: string, right: string): number {
  const leftNumber = Number(/^sjtu_rule_(\d+)$/.exec(left)?.[1] ?? Number.MAX_SAFE_INTEGER);
  const rightNumber = Number(/^sjtu_rule_(\d+)$/.exec(right)?.[1] ?? Number.MAX_SAFE_INTEGER);
  return leftNumber - rightNumber;
}

function referenceDisplayFindings(run: PaperLintRuleRun): PaperLintFinding[] {
  return referenceInfoFindings(run).map(finding => ({ ...finding, prompt_only: true }));
}

export function referencePresentationRun(run: PaperLintRuleRun): PaperLintRuleRun {
  if (run.rule_id !== 'sjtu_rule_32') return run;
  const findings = referenceDisplayFindings(run);
  const unresolved = findings.filter(f => f.reference_review === 'insufficient_evidence').length;
  const suspected = findings.length - unresolved;
  return { ...run, findings, severity: 'info', ...(run.execution_status === 'completed' ? {
    publication_status: suspected ? 'ALERT' as const : 'NO_ALERT' as const,
    // Keep a backend resource-status explanation (quota, rate limit, or
    // temporary service outage) instead of replacing it with a false success.
    message: referenceResourcesUnavailable(run)
      ? referenceResourceMessage(run)
      : [suspected ? `发现 ${suspected} 条疑似不存在的引用，请逐条人工复核。` : null,
        unresolved ? `${unresolved} 条引用核验证据不足，请人工核查（提示）。` : null,
      ].filter(Boolean).join(' ') || run.message || '未发现疑似不存在的引用。',
  } : {}) };
}

export function paperLintPresentation(result: PaperLintResult): PaperLintResult {
  const rule_runs = result.rule_runs.map(referencePresentationRun);
  return { ...result, rule_runs, summary: displayedReportSummary({ ...result, rule_runs }) };
}

export function flattenPaperLintFindings(result: Pick<PaperLintResult, 'rule_runs'>): PaperLintFindingItem[] {
  const items: PaperLintFindingItem[] = [];
  for (const ruleRun of result.rule_runs || []) {
    for (const finding of ruleRun.rule_id === numericRule ? numericDisplayFindings(ruleRun) : ruleRun.rule_id === 'sjtu_rule_32' ? referenceDisplayFindings(ruleRun) : ruleRun.findings || []) {
      items.push({
        key: finding.finding_id || `${ruleRun.rule_id}-${items.length}`,
        finding,
        ruleRun: { ...ruleRun, severity: ruleRun.rule_id === 'sjtu_rule_32' ? 'info' : (finding as PaperLintFinding & { severity?: PaperLintRuleRun['severity'] }).severity || ruleRun.severity },
        index: items.length,
      });
    }
  }
  const ordered = items.sort(
      (left, right) =>
        comparePaperLintRuleIds(left.ruleRun.rule_id, right.ruleRun.rule_id) ||
        pageNumber(left) - pageNumber(right) ||
        topPosition(left) - topPosition(right) ||
        left.index - right.index,
    );
  const severityOrder = { error: 0, warning: 1, info: 2 };
  const numericFindings = ordered.filter(item => item.ruleRun.rule_id === numericRule)
    .sort((left, right) => severityOrder[left.ruleRun.severity] - severityOrder[right.ruleRun.severity]);
  let numericIndex = 0;
  return ordered.map((item, index) => ({ ...(item.ruleRun.rule_id === numericRule ? numericFindings[numericIndex++] : item), index }));
}

export function findingPageLabel(item: PaperLintFindingItem): string | null {
  const pages = new Set<number>();
  const addLocation = (location: PaperLintFinding['location']) => {
    if (!location) return;
    pages.add(location.page_number);
    if (location.type === 'pdf_bbox') location.rects.forEach((rect) => pages.add(rect.page_number));
  };
  addLocation(item.finding.location);
  item.finding.anchors?.forEach((anchor) => addLocation(anchor.location));
  const values = Array.from(pages)
    .filter((page) => Number.isInteger(page) && page >= 1)
    .sort((a, b) => a - b);
  return values.length ? values.join('、') : null;
}

export function compilerPublicationLabel(run: PaperLintRuleRun): string | null {
  if (referenceResourcesUnavailable(run)) return referenceDisplayFindings(run).some(f => f.reference_review !== 'insufficient_evidence') ? '发现问题（部分未检测）' : '未能检测';
  if (!['sjtu_rule_31', 'sjtu_rule_32', 'sjtu_rule_33'].includes(run.rule_id) || !run.publication_status) return null;
  if (run.execution_status === 'error') return '执行失败';
  if (run.rule_id === 'sjtu_rule_32' && referenceDisplayFindings(run).length) return '待人工复核';
  return run.publication_status === 'ALERT' ? '发现问题' : '未触发告警';
}

export function compilerPublicationSummary(result: PaperLintResult): string | null {
  if (!result.rule_runs.some((run) => compilerPublicationLabel(run) !== null)) return null;
  if (result.summary.finding_count) return null;
  if (result.summary.error_rule_count) return '部分规则执行失败';
  if (result.summary.unsupported_rule_count) return null;
  return '未触发告警';
}
