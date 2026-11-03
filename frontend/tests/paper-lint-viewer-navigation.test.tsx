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
});
