import type { PaperLintFinding, PaperLintResult, PaperLintRuleRun } from '../../api/paperLint';

export type PaperLintFindingItem = {
  key: string;
  finding: PaperLintFinding;
  ruleRun: PaperLintRuleRun;
  index: number;
};

export type RuleExecutionWarning = { title: string; reason: string; suggestion: string };
const numericRule = 'abstract_numeric_consistency_check';
export function numericExecutionWarnings(run?: PaperLintRuleRun): RuleExecutionWarning[] {
  if (!run) return [];
  const params = run.params || {};
  const names: Record<string, string> = { abstract_numeric: '摘要中存在可核验的数值型论点', contribution_mapping: '数值型论点能够对应研究贡献与研究章节', experiment_subsection: '存在可信对应的实验章节或子章节' };
  const conditions = Array.isArray(params.preconditions) ? params.preconditions : [];
  const failed = conditions.filter(c => c.passed === false && c.status !== 'skipped');
  const warnings = failed.map(c => ({ title: `论点论据一致性检测：${names[c.id] || c.id}`, reason: String(c.reason || '未满足该前置条件'), suggestion: String(c.suggestion || '请调整论文中的相应摘要、研究贡献或实验章节组织后重新检测。') }));
  if (run.execution_status === 'error' || params.failure || (Array.isArray(params.validation_errors) && params.validation_errors.length)) {
    warnings.push({ title: '论点论据一致性检测未完成', reason: '部分核验因服务请求或结果校验失败而未完成。已完成的有效结果仍予以保留。', suggestion: '请稍后重试；若持续失败，请联系管理员检查运行记录。' });
  }
  return warnings;
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

export function flattenPaperLintFindings(result: Pick<PaperLintResult, 'rule_runs'>): PaperLintFindingItem[] {
  const items: PaperLintFindingItem[] = [];
  for (const ruleRun of result.rule_runs || []) {
    for (const finding of ruleRun.rule_id === numericRule ? numericDisplayFindings(ruleRun) : ruleRun.findings || []) {
      items.push({
        key: finding.finding_id || `${ruleRun.rule_id}-${items.length}`,
        finding,
        ruleRun: { ...ruleRun, severity: (finding as PaperLintFinding & { severity?: PaperLintRuleRun['severity'] }).severity || ruleRun.severity },
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
  return run.publication_status === 'ALERT' ? '发现问题' : '未触发告警';
}

export function compilerPublicationSummary(result: PaperLintResult): string | null {
  if (!result.rule_runs.some((run) => compilerPublicationLabel(run) !== null)) return null;
  if (result.summary.finding_count) return null;
  if (result.summary.error_rule_count) return '部分规则执行失败';
  if (result.summary.unsupported_rule_count) return null;
  return '未触发告警';
}
