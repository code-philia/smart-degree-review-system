import { createRef } from 'react';
import { act, render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { PdfViewer, type PdfViewerHandle } from '../src/components/paperLint/PdfViewer';
import type { PaperLintPdfAnnotation } from '../src/components/paperLint/geometry';

const { scrollPageIntoView, readyScale, viewerEvents } = vi.hoisted(() => ({
  scrollPageIntoView: vi.fn(), readyScale: vi.fn(),
  viewerEvents: [] as { dispatch: (name: string, event?: { pageNumber?: number }) => void; listenerCount: (name: string) => number }[],
}));

vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({GlobalWorkerOptions: {}, version: 'test'}));
vi.mock('pdfjs-dist/legacy/web/pdf_viewer.mjs', () => {
  class EventBus {
    private listeners = new Map<string, Set<(event: { pageNumber?: number }) => void>>();
    constructor() { viewerEvents.push(this); }
    on(name: string, callback: (event: { pageNumber?: number }) => void) {
      const values = this.listeners.get(name) || new Set();
      values.add(callback);
      this.listeners.set(name, values);
    }
    off(name: string, callback: (event: { pageNumber?: number }) => void) { this.listeners.get(name)?.delete(callback); }
    dispatch(name: string, event = {}) { this.listeners.get(name)?.forEach((callback) => callback(event)); }
    listenerCount(name: string) { return this.listeners.get(name)?.size || 0; }
  }
  class PDFLinkService {
    setViewer() {}
    setDocument() {}
  }
  class PDFViewer {
    currentScale = 1;
    private ready = false;
    set currentScaleValue(value: string) { if (this.ready) readyScale(value); }
    constructor(private options: { eventBus: EventBus }) {}
    setDocument() { setTimeout(() => { this.ready = true; this.options.eventBus.dispatch('pagesinit'); }, 0); }
    scrollPageIntoView(options: { pageNumber: number }) { scrollPageIntoView(options); }
    cleanup() {}
  }
  return { EventBus, PDFLinkService, PDFViewer };
});

const rect = { x1: 85, y1: 247, x2: 517, y2: 263, width: 595, height: 842, page_number: 99 };
const annotation: PaperLintPdfAnnotation = {
  findingKey: 'finding-99', ruleId: 'sjtu_rule_24', severity: 'warning',
  pageNumber: 99, boundingRect: rect, rects: [rect],
};

describe('PDF viewer startup navigation', () => {
  it('fits the page after PDF.js has created the page views', async () => {
    readyScale.mockClear();
    render(<PdfViewer pdfDocument={{} as PDFDocumentProxy} scale="page-width"
      annotationsByPage={new Map()} activeFindingKey={null} activeAnchorId={null}
      density="focus" onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    await waitFor(() => expect(readyScale).toHaveBeenCalledWith('page-width'));
  });
  it('jumps to a pending issue when PDF.js announces that pages are ready', async () => {
    const ref = createRef<PdfViewerHandle>();
    render(<PdfViewer ref={ref} pdfDocument={{} as PDFDocumentProxy} scale="page-width"
      annotationsByPage={new Map()} activeFindingKey="finding-99" activeAnchorId={null}
      density="focus" onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    ref.current?.scrollToAnnotation(annotation);
    await waitFor(() => expect(scrollPageIntoView).toHaveBeenCalledWith({ pageNumber: 99 }));
  });

  it('reports page events without rebuilding the reader and removes the listener on unmount', async () => {
    const first = vi.fn(), next = vi.fn();
    const props = { pdfDocument: { numPages: 120 } as PDFDocumentProxy, scale: 'page-width' as const,
      annotationsByPage: new Map(), activeFindingKey: null, activeAnchorId: null,
      density: 'focus' as const, onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
    const { rerender, unmount } = render(<PdfViewer {...props} onPageChange={first} />);
    await waitFor(() => expect(first).toHaveBeenCalledWith(1));
    const bus = viewerEvents.at(-1)!;
    const count = viewerEvents.length;
    act(() => bus.dispatch('pagechanging', { pageNumber: 17 }));
    expect(first).toHaveBeenLastCalledWith(17);
    rerender(<PdfViewer {...props} onPageChange={next} />);
    expect(viewerEvents).toHaveLength(count);
    act(() => bus.dispatch('pagechanging', { pageNumber: 18 }));
    expect(next).toHaveBeenLastCalledWith(18);
    for (const pageNumber of [0, 121, NaN]) act(() => bus.dispatch('pagechanging', { pageNumber }));
    expect(next).toHaveBeenCalledTimes(1);
    unmount();
    expect(bus.listenerCount('pagechanging')).toBe(0);
    act(() => bus.dispatch('pagechanging', { pageNumber: 19 }));
    expect(next).toHaveBeenCalledTimes(1);
  });

  it('waits for the text layer and paints only the clicked numeric value', async () => {
    const focused: PaperLintPdfAnnotation = { ...annotation, ruleId: 'abstract_numeric_consistency_check',
      anchorId: 'd1:t1', focusTerms: ['3.57'] };
    const ref = createRef<PdfViewerHandle>();
    const { getByTestId, unmount } = render(<PdfViewer ref={ref}
      pdfDocument={{ numPages: 120 } as PDFDocumentProxy} scale="page-width"
      annotationsByPage={new Map([[99, [focused]]])} activeFindingKey="finding-99" activeAnchorId="d1:t1"
      density="focus" onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    await waitFor(() => expect(viewerEvents.at(-1)?.listenerCount('pagesinit')).toBe(1));
    const bus = viewerEvents.at(-1)!;
    const container = getByTestId('paper-lint-pdf-viewer');
    const page = document.createElement('div');
    page.className = 'page'; page.dataset.pageNumber = '99';
    Object.defineProperties(page, { clientWidth: { value: 595 }, clientHeight: { value: 842 } });
    page.getBoundingClientRect = () => ({ left: 0, top: 0, width: 595, height: 842, right: 595,
      bottom: 842, x: 0, y: 0, toJSON() {} });
    container.querySelector('.pdfViewer')!.append(page);
    const scroll = vi.fn(); container.scrollTo = scroll;
    act(() => bus.dispatch('pagesinit'));
    act(() => bus.dispatch('pagerendered', { pageNumber: 99 }));
    expect(page.querySelectorAll('.paper-lint-overlay-host rect')).toHaveLength(0);
    ref.current?.scrollToAnnotation(focused);
    act(() => bus.dispatch('pagerendered', { pageNumber: 99 }));
    expect(scroll).not.toHaveBeenCalled();
    const original = Object.getOwnPropertyDescriptor(Range.prototype, 'getClientRects');
    Object.defineProperty(Range.prototype, 'getClientRects', { configurable: true, value: () =>
      [{ left: 120, top: 250, right: 142, bottom: 262, width: 22, height: 12 }] });
    try {
      const text = document.createElement('div'); text.className = 'textLayer';
      text.innerHTML = '<span>平均误差为3.57 m。后面还有其他不相关的段落。</span>'; page.append(text);
      act(() => bus.dispatch('textlayerrendered', { pageNumber: 99 }));
      await waitFor(() => expect(page.querySelectorAll('.paper-lint-overlay-host rect')).toHaveLength(1));
      expect(page.querySelector('.paper-lint-overlay-host rect')).toHaveAttribute('width', '22');
      expect(scroll).toHaveBeenCalledTimes(1);
      // PDF.js can replace a page's children while recycling a distant page.
      page.querySelector('.paper-lint-overlay-host')!.remove();
      act(() => bus.dispatch('textlayerrendered', { pageNumber: 99 }));
      act(() => bus.dispatch('pagerendered', { pageNumber: 99 }));
      await waitFor(() => expect(page.querySelectorAll('.paper-lint-overlay-host rect')).toHaveLength(1));
      text.remove();
      ref.current?.scrollToAnnotation(focused);
      act(() => bus.dispatch('pagerendered', { pageNumber: 99 }));
      expect(scroll).toHaveBeenCalledTimes(1);
      const freshText = text.cloneNode(true); page.append(freshText);
      act(() => bus.dispatch('textlayerrendered', { pageNumber: 99 }));
      expect(scroll).toHaveBeenCalledTimes(2);
      unmount();
      expect(bus.listenerCount('textlayerrendered')).toBe(0);
    } finally {
      if (original) Object.defineProperty(Range.prototype, 'getClientRects', original);
      else delete (Range.prototype as any).getClientRects;
    }
  });
});
