import type { PDFDocumentProxy } from 'pdfjs-dist';
import { findingPageLabel, type PaperLintFindingItem } from './model';

export type PdfPageLabels = Record<number, string>;
type NativeText = { str: string; transform: number[]; width: number; height: number };
type Viewport = { width: number; height: number; convertToViewportPoint: (x: number, y: number) => number[] };
type FooterLabel = { label: string; ordinal: number; style: 'arabic' | 'roman' };

function parseLabel(value: string): FooterLabel | null {
  const label = value
    .trim()
    .replace(/^[-–—·•\s]+|[-–—·•\s]+$/g, '')
    .replace(/^第\s*|\s*页$/g, '')
    .trim();
  if (/^\d{1,5}$/.test(label)) return { label, ordinal: Number(label), style: 'arabic' };
  const roman = label.normalize('NFKC').toUpperCase();
  if (!roman || !/^(?=.)M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$/.test(roman)) return null;
  const values: Record<string, number> = { I: 1, V: 5, X: 10, L: 50, C: 100, D: 500, M: 1000 };
  let ordinal = 0;
  for (let i = 0; i < roman.length; i++)
    ordinal += values[roman[i]] * (values[roman[i]] < (values[roman[i + 1]] || 0) ? -1 : 1);
  return { label, ordinal, style: 'roman' };
}

/** Inspect only native text in the bottom margin. Body/table numbers are not page labels. */
export function extractFooterLabel(items: unknown[], viewport: Viewport): FooterLabel | null {
  const rows: { y: number; items: { x: number; right: number; text: string }[] }[] = [];
  for (const value of items) {
    const item = value as Partial<NativeText>;
    if (typeof item.str !== 'string' || !item.str.trim() || !Array.isArray(item.transform) || item.transform.length < 6)
      continue;
    const [x, y] = viewport.convertToViewportPoint(item.transform[4], item.transform[5]);
    if (
      !Number.isFinite(x) ||
      !Number.isFinite(y) ||
      y < viewport.height * 0.91 ||
      y > viewport.height + 2 ||
      x < 0 ||
      x > viewport.width ||
      (item.height || 0) > 20
    )
      continue;
    let row = rows.find((candidate) => Math.abs(candidate.y - y) <= 2.5);
    if (!row) {
      row = { y, items: [] };
      rows.push(row);
    }
    row.items.push({ x, right: x + Math.abs(item.width || 0), text: item.str.trim() });
  }
  for (const row of rows.sort((a, b) => b.y - a.y)) {
    const groups: { right: number; text: string }[] = [];
    for (const item of row.items.sort((a, b) => a.x - b.x)) {
      const previous = groups.at(-1);
      if (previous && item.x - previous.right < 25) {
        previous.text += item.text;
        previous.right = item.right;
      } else groups.push({ right: item.right, text: item.text });
    }
    const matches = groups
      .map((group) => parseLabel(group.text))
      .filter((label): label is FooterLabel => Boolean(label));
    if (matches.length > 1) return null;
    if (matches.length === 1) return matches[0];
  }
  return null;
}

type Cache = { metadata: Promise<string[] | null>; footers: Map<number, Promise<FooterLabel | null>> };
const documents = new WeakMap<PDFDocumentProxy, Cache>();
function cacheFor(document: PDFDocumentProxy): Cache {
  const existing = documents.get(document);
  if (existing) return existing;
  const cache: Cache = {
    footers: new Map(),
    metadata: Promise.resolve()
      .then(() => (typeof document.getPageLabels === 'function' ? document.getPageLabels() : null))
      .catch(() => null),
  };
  documents.set(document, cache);
  return cache;
}
function aborted(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('已取消页码读取', 'AbortError');
}
function footerFor(document: PDFDocumentProxy, cache: Cache, page: number): Promise<FooterLabel | null> {
  if (page < 1 || page > document.numPages) return Promise.resolve(null);
  const existing = cache.footers.get(page);
  if (existing) return existing;
  const result = Promise.resolve()
    .then(async () => {
      const pdfPage = await document.getPage(page);
      const content = await pdfPage.getTextContent();
      return extractFooterLabel(content.items, pdfPage.getViewport({ scale: 1 }));
    })
    .catch(() => {
      cache.footers.delete(page);
      return null;
    });
  cache.footers.set(page, result);
  return result;
}

/** Read finding pages plus immediate neighbors, with two workers and a per-document cache. */
export async function resolvePdfPageLabels(
  document: PDFDocumentProxy,
  pages: number[],
  options: { signal?: AbortSignal; onUpdate?: (labels: PdfPageLabels) => void } = {},
): Promise<PdfPageLabels> {
  aborted(options.signal);
  if (!Number.isInteger(document.numPages) || document.numPages < 1) return {};
  const targets = [...new Set(pages)].filter(
    (page) => Number.isInteger(page) && page >= 1 && page <= document.numPages,
  );
  const cache = cacheFor(document),
    metadata = await cache.metadata;
  aborted(options.signal);
  const explicitMetadata =
    metadata?.length === document.numPages && metadata.some((label, index) => label && label !== String(index + 1));
  const result: PdfPageLabels = {};
  let next = 0,
    completed = 0;
  async function worker() {
    while (next < targets.length) {
      aborted(options.signal);
      const page = targets[next++];
      const footer = await footerFor(document, cache, page);
      aborted(options.signal);
      let confirmed = document.numPages === 1;
      if (footer && !confirmed) {
        // A section can restart at 1 or use Roman preliminaries: never extrapolate a global offset.
        for (const delta of [-1, 1]) {
          const neighbor = await footerFor(document, cache, page + delta);
          aborted(options.signal);
          if (neighbor?.style === footer.style && neighbor.ordinal === footer.ordinal + delta) {
            confirmed = true;
            break;
          }
        }
      }
      if (footer && confirmed) result[page] = footer.label;
      else if (
        explicitMetadata &&
        typeof metadata?.[page - 1] === 'string' &&
        metadata[page - 1].trim() &&
        metadata[page - 1].length <= 40
      )
        result[page] = metadata[page - 1].trim();
      completed++;
      if (completed % 4 === 0) options.onUpdate?.({ ...result });
    }
  }
  await Promise.all([worker(), worker()]);
  aborted(options.signal);
  options.onUpdate?.({ ...result });
  return result;
}

export function displayFindingPages(item: PaperLintFindingItem, labels: PdfPageLabels): string | null {
  const pages = findingPageLabel(item)?.split('、').map(Number);
  if (!pages?.length) return null;
  if (pages.every((page) => labels[page])) return `第 ${[...new Set(pages.map((page) => labels[page]))].join('、')} 页`;
  if (pages.every((page) => !labels[page])) return `PDF 第 ${pages.join('、')} 页`;
  return pages.map((page) => (labels[page] ? `第 ${labels[page]} 页` : `PDF 第 ${page} 页`)).join('、');
}
