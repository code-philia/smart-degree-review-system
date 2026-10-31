import { describe, expect, it, vi } from 'vitest';
import { extractFooterLabel, resolvePdfPageLabels, displayFindingPages } from '../src/components/paperLint/pageLabels';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

const text = (str: string, x = 292, y = 30, width = 12) => ({
  str,
  width,
  height: 10,
  transform: [10, 0, 0, 10, x, y],
});
const viewport = { width: 595, height: 842, convertToViewportPoint: (x: number, y: number) => [x, 842 - y] };
const footer = (label: string) => [text('正文', 80, 300, 40), text(label)];
function documentWith(labels: Record<number, string>, metadata: string[] | null = null, numPages = 120) {
  const getTextContent = vi.fn(async (page: number) => ({ items: footer(labels[page] || '正文没有页码') }));
  const getPage = vi.fn(async (page: number) => ({
    getViewport: () => viewport,
    getTextContent: () => getTextContent(page),
  }));
  return {
    doc: { numPages, getPage, getPageLabels: vi.fn(async () => metadata) } as unknown as PDFDocumentProxy,
    getPage,
    getTextContent,
  };
}

describe('printed PDF page labels', () => {
  it('reads isolated footer digits and split Roman glyphs, rejecting body numbers and ambiguous footer rows', () => {
    expect(extractFooterLabel(footer('33'), viewport)?.label).toBe('33');
    expect(extractFooterLabel([text('I', 290, 30, 4), text('V', 295, 30, 5)], viewport)?.label).toBe('IV');
    expect(extractFooterLabel([text('33', 290, 300)], viewport)).toBeNull();
    expect(extractFooterLabel([text('33', 100, 30), text('49', 450, 30)], viewport)).toBeNull();
    expect(extractFooterLabel([text('10.5', 292, 30)], viewport)).toBeNull();
  });
  it('maps natural page 42 to printed page 33 while keeping Roman and restarted numbering independent', async () => {
    const { doc } = documentWith({ 3: 'I', 4: 'II', 5: '1', 6: '2', 41: '32', 42: '33', 43: '34' });
    expect(await resolvePdfPageLabels(doc, [4, 5, 42])).toEqual({ 4: 'II', 5: '1', 42: '33' });
  });
  it('does not infer one global offset or trust a lone footer table value', async () => {
    const { doc } = documentWith({ 42: '33', 80: '77' });
    expect(await resolvePdfPageLabels(doc, [42, 80])).toEqual({});
  });
  it('uses explicit PDF page labels and does not confuse default natural labels with printed labels', async () => {
    const explicit = documentWith({}, ['封面', 'I', 'II', '1', '2'], 5);
    expect(await resolvePdfPageLabels(explicit.doc, [4])).toEqual({ 4: '1' });
    const natural = documentWith({}, ['1', '2', '3', '4', '5'], 5);
    expect(await resolvePdfPageLabels(natural.doc, [4])).toEqual({});
  });
  it('caches native text per PDF and supports cancellation without partial stale updates', async () => {
    const { doc, getTextContent } = documentWith({ 41: '32', 42: '33', 43: '34' });
    await resolvePdfPageLabels(doc, [42]);
    const count = getTextContent.mock.calls.length;
    await resolvePdfPageLabels(doc, [42]);
    expect(getTextContent).toHaveBeenCalledTimes(count);
    const controller = new AbortController();
    controller.abort();
    const update = vi.fn();
    await expect(
      resolvePdfPageLabels(doc, [42], { signal: controller.signal, onUpdate: update }),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(update).not.toHaveBeenCalled();
  });
  it('formats printed labels but explicitly falls back to physical PDF pages', () => {
    const item = {
      finding: { location: { type: 'pdf_page', page_number: 42 }, anchors: [] },
    } as unknown as PaperLintFindingItem;
    expect(displayFindingPages(item, { 42: '33' })).toBe('第 33 页');
    expect(displayFindingPages(item, {})).toBe('PDF 第 42 页');
  });
});
