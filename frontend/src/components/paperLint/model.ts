import type { PaperLintFinding, PaperLintResult, PaperLintRuleRun } from '../../api/paperLint';

export type PaperLintFindingItem = {
  key: string;
  finding: PaperLintFinding;
  ruleRun: PaperLintRuleRun;
  index: number;
};

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

export function flattenPaperLintFindings(result: PaperLintResult): PaperLintFindingItem[] {
  const items: PaperLintFindingItem[] = [];
  for (const ruleRun of result.rule_runs || []) {
    for (const finding of ruleRun.findings || []) {
      items.push({
        key: finding.finding_id || `${ruleRun.rule_id}-${items.length}`,
        finding,
        ruleRun,
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
