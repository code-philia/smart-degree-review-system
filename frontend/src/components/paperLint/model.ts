import type { PaperLintFinding, PaperLintResult, PaperLintRuleRun } from '../../api/paperLint';

export type PaperLintFindingItem = {
  key: string;
  finding: PaperLintFinding;
  ruleRun: PaperLintRuleRun;
  index: number;
};

export type RuleExecutionWarning = {
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

export function numericExecutionWarnings(run?: PaperLintRuleRun): RuleExecutionWarning[] {
  if (!run) return [];
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
  const failed = conditions.filter(c => c.passed === false && c.status !== 'skipped');
  const warnings = failed.map(c => {
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
    warnings.push({ title: '论点论据一致性检测未完成', reason: '部分核验因服务请求或结果校验失败而未完成。已完成的有效结果仍予以保留。', suggestion: '请稍后重试；若持续失败，请联系管理员检查运行记录。' });
  }
  return warnings.map(warning => ({ ...warning, ruleId: numericRule }));
}

export function numericDisplayFindings(run: PaperLintRuleRun): PaperLintFinding[] {
  const params = run.params || {};
  const conditions = Array.isArray(params.preconditions) ? params.preconditions : [];
  if (conditions.some(c => c.passed === false)) return [];
  const rows = Array.isArray(params.numeric_results) ? params.numeric_results : null;
  if (!rows) return run.findings || [];
  const errors = Array.isArray(params.validation_errors) ? params.validation_errors : [];
  return rows.filter(row => ['inconsistent', 'inconclusive'].includes(row.status)
    && !errors.some(error => error.declaration_id === row.declaration_id)
    && !/^结果校验未通过|.*核验执行失败/.test(String(row.reason || '')))
    .map(row => {
      const old = run.findings?.find(f => f.finding_id === `${numericRule}_${row.declaration_id}`);
      const evidence = Array.isArray(row.evidence)
        ? row.evidence.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
        : [];
      const evidenceLabels = new Map(
        evidence
          .map(item => String(item.candidate_id || item.id || ''))
          .filter(Boolean)
          .map((id, index) => [id, `实验结果证据${index + 1}`]),
      );
      let fallbackEvidenceIndex = evidenceLabels.size + 1;
      const readableReason = String(row.reason || '')
        .replace(/\b[dD]\d+\s*:\s*[A-Za-z]\d+\b/g, id => {
        const existing = evidenceLabels.get(id.replace(/\s/g, ''));
        if (existing) return existing;
        const label = `实验结果证据${fallbackEvidenceIndex++}`;
        evidenceLabels.set(id.replace(/\s/g, ''), label);
        return label;
        })
        // Page navigation is rendered separately and uses the verified anchor
        // locations; do not expose model-supplied page claims in the explanation.
        .replace(/第\s*\d+(?:\s*[、,]\s*\d+)*\s*页/g, '')
        .replace(/页码\s*[:：]?\s*\d+(?:\s*[、,]\s*\d+)*/g, '')
        .replace(/[ \t]{2,}/g, ' ')
        .replace(/\s+([，。；：、])/g, '$1')
        .trim();
      const abstractAnchors = Array.isArray(row.abstract_anchors)
        ? row.abstract_anchors.map(anchor => ({ ...anchor, label: '摘要数值论点' }))
        : [];
      const evidenceAnchors = Array.isArray(row.evidence_anchors)
        ? row.evidence_anchors.map((anchor, index) => ({
            ...anchor,
            label: evidenceLabels.get(String(anchor.anchor_id || '')) || `实验结果证据${index + 1}`,
          }))
        : [];
      const anchors = [...abstractAnchors, ...evidenceAnchors];
      return { ...old, finding_id: `${numericRule}_${row.declaration_id}`, rule_id: numericRule,
        severity: row.status === 'inconsistent' ? 'warning' : 'info',
        message: `${row.status === 'inconsistent' ? '论点与论据不一致' : '论据不明确'}：${readableReason}`,
        suggestion: row.suggestion || '', anchors: anchors.length ? anchors : old?.anchors,
        location: anchors[0]?.location || old?.location } as PaperLintFinding;
    });
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
  return (run.findings || []).filter(finding => !finding.prompt_only || finding.reference_review === 'supported_suspicion')
    .map(finding => ({ ...finding, prompt_only: true, reference_review: 'supported_suspicion' as const }));
}

export function referencePresentationRun(run: PaperLintRuleRun): PaperLintRuleRun {
  if (run.rule_id !== 'sjtu_rule_32') return run;
  const findings = referenceDisplayFindings(run);
  return { ...run, findings, severity: 'info', ...(run.execution_status === 'completed' ? {
    publication_status: findings.length ? 'ALERT' as const : 'NO_ALERT' as const,
    message: findings.length ? `发现 ${findings.length} 条疑似不存在的引用，请逐条人工复核。` : '未发现疑似不存在的引用。',
  } : {}) };
}

export function paperLintPresentation(result: PaperLintResult): PaperLintResult {
  if (!result.rule_runs.some(run => run.rule_id === 'sjtu_rule_32')) return result;
  const rule_runs = result.rule_runs.map(referencePresentationRun);
  const findings = flattenPaperLintFindings({ rule_runs });
  return { ...result, rule_runs, summary: { ...result.summary,
    finding_count: findings.length,
    error_finding_count: findings.filter(item => item.ruleRun.severity === 'error').length,
    warning_finding_count: findings.filter(item => item.ruleRun.severity === 'warning').length,
    info_finding_count: findings.filter(item => item.ruleRun.severity === 'info').length,
    issue_rule_count: new Set(findings.map(item => item.ruleRun.rule_id)).size,
  } };
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
  return items
    .sort(
      (left, right) =>
        comparePaperLintRuleIds(left.ruleRun.rule_id, right.ruleRun.rule_id) ||
        pageNumber(left) - pageNumber(right) ||
        topPosition(left) - topPosition(right) ||
        left.index - right.index,
    )
    .map((item, index) => ({ ...item, index }));
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
