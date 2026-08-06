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
        pageNumber(left) - pageNumber(right) || topPosition(left) - topPosition(right) || left.index - right.index,
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
