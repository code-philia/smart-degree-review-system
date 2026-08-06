import type { PaperLintFindingAnchor, PdfBBoxLocation, PdfRect } from '../../api/paperLint';
import type { PaperLintFindingItem } from './model';

export type PaperLintPdfAnnotation = {
  findingKey: string;
  ruleId: string;
  severity: PaperLintFindingItem['ruleRun']['severity'];
  pageNumber: number;
  boundingRect: PdfRect;
  rects: PdfRect[];
  textExcerpt?: string | null;
  anchorId?: string;
  anchorRole?: string;
  anchorLabel?: string | null;
};

export type PaperLintPdfTarget =
  { type: 'none' } | { type: 'page'; pageNumber: number } | { type: 'bbox'; annotation: PaperLintPdfAnnotation };

export function isValidPdfRect(rect: PdfRect) {
  return (
    Number.isFinite(rect.x1) &&
    Number.isFinite(rect.y1) &&
    Number.isFinite(rect.x2) &&
    Number.isFinite(rect.y2) &&
    Number.isFinite(rect.width) &&
    Number.isFinite(rect.height) &&
    rect.width > 0 &&
    rect.height > 0 &&
    Number.isInteger(rect.page_number) &&
    rect.page_number >= 1 &&
    rect.x2 > rect.x1 &&
    rect.y2 > rect.y1
  );
}

function unionPdfRects(rects: PdfRect[]): PdfRect {
  const first = rects[0];
  return {
    x1: Math.min(...rects.map((rect) => rect.x1)),
    y1: Math.min(...rects.map((rect) => rect.y1)),
    x2: Math.max(...rects.map((rect) => rect.x2)),
    y2: Math.max(...rects.map((rect) => rect.y2)),
    width: first.width,
    height: first.height,
    page_number: first.page_number,
  };
}

function locationAnnotations(item: PaperLintFindingItem, location: PdfBBoxLocation, anchor?: PaperLintFindingAnchor) {
  const grouped = new Map<number, PdfRect[]>();
  const sourceRects = location.rects.length > 0 ? location.rects : [location.bounding_rect];
  for (const rect of sourceRects) {
    if (!isValidPdfRect(rect)) continue;
    grouped.set(rect.page_number, [...(grouped.get(rect.page_number) || []), rect]);
  }
  return Array.from(grouped.entries())
    .sort(([a], [b]) => a - b)
    .map(
      ([pageNumber, rects]) =>
        ({
          findingKey: item.key,
          ruleId: item.ruleRun.rule_id,
          severity: item.ruleRun.severity,
          pageNumber,
          boundingRect: unionPdfRects(rects),
          rects,
          textExcerpt: location.text_excerpt,
          anchorId: anchor?.anchor_id,
          anchorRole: anchor?.role,
          anchorLabel: anchor?.label,
        }) satisfies PaperLintPdfAnnotation,
    );
}

export function findingAnnotations(item: PaperLintFindingItem): PaperLintPdfAnnotation[] {
  const annotations: PaperLintPdfAnnotation[] = [];
  if (item.finding.location?.type === 'pdf_bbox') {
    annotations.push(...locationAnnotations(item, item.finding.location));
  }
  for (const anchor of item.finding.anchors || []) {
    if (anchor.location.type === 'pdf_bbox') annotations.push(...locationAnnotations(item, anchor.location, anchor));
  }
  const deduped = new Map<string, PaperLintPdfAnnotation>();
  for (const annotation of annotations) {
    const signature = `${annotation.findingKey}:${annotation.pageNumber}:${annotation.rects.map((rect) => `${rect.x1}:${rect.y1}:${rect.x2}:${rect.y2}`).join('|')}`;
    const existing = deduped.get(signature);
    if (!existing || (!existing.anchorId && annotation.anchorId)) deduped.set(signature, annotation);
  }
  return Array.from(deduped.values());
}

export function buildAnnotations(items: PaperLintFindingItem[]) {
  return items.flatMap(findingAnnotations);
}

export function groupAnnotationsByPage(annotations: PaperLintPdfAnnotation[]) {
  const grouped = new Map<number, PaperLintPdfAnnotation[]>();
  for (const annotation of annotations) {
    grouped.set(annotation.pageNumber, [...(grouped.get(annotation.pageNumber) || []), annotation]);
  }
  return grouped;
}

export function findingTarget(item: PaperLintFindingItem | null, anchorId?: string | null): PaperLintPdfTarget {
  if (!item) return { type: 'none' };
  const anchor = anchorId ? item.finding.anchors?.find((candidate) => candidate.anchor_id === anchorId) : null;
  const location = anchor?.location || item.finding.location || item.finding.anchors?.[0]?.location;
  if (!location) return { type: 'none' };
  if (location.type === 'pdf_bbox') {
    const annotation = locationAnnotations(item, location, anchor || undefined)[0];
    return annotation ? { type: 'bbox', annotation } : { type: 'page', pageNumber: location.page_number };
  }
  return { type: 'page', pageNumber: location.page_number };
}

export function getPdfRectCenter(rect: PdfRect) {
  return { x: rect.x1 + (rect.x2 - rect.x1) / 2, y: rect.y1 + (rect.y2 - rect.y1) / 2 };
}

export function pageSize(annotations: PaperLintPdfAnnotation[]) {
  const rect = annotations[0]?.boundingRect || annotations[0]?.rects[0];
  return rect && rect.width > 0 && rect.height > 0 ? { width: rect.width, height: rect.height } : null;
}
