import { createRef } from 'react';
import { render, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { PdfViewer, type PdfViewerHandle } from '../src/components/paperLint/PdfViewer';
import type { PaperLintPdfAnnotation } from '../src/components/paperLint/geometry';

const { scrollPageIntoView } = vi.hoisted(() => ({ scrollPageIntoView: vi.fn() }));

vi.mock('pdfjs-dist', () => ({}));
vi.mock('pdfjs-dist/web/pdf_viewer.mjs', () => {
  class EventBus {
    private listeners = new Map<string, Set<() => void>>();
    on(name: string, callback: () => void) {
      const values = this.listeners.get(name) || new Set();
      values.add(callback);
      this.listeners.set(name, values);
    }
    off(name: string, callback: () => void) { this.listeners.get(name)?.delete(callback); }
    dispatch(name: string) { this.listeners.get(name)?.forEach((callback) => callback()); }
  }
  class PDFLinkService {
    setViewer() {}
    setDocument() {}
  }
  class PDFViewer {
    currentScale = 1;
    currentScaleValue = 'page-width';
    constructor(private options: { eventBus: EventBus }) {}
    setDocument() { setTimeout(() => this.options.eventBus.dispatch('pagesinit'), 0); }
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
  it('jumps to a pending issue when PDF.js announces that pages are ready', async () => {
    const ref = createRef<PdfViewerHandle>();
    render(<PdfViewer ref={ref} pdfDocument={{} as PDFDocumentProxy} scale="page-width"
      annotationsByPage={new Map()} activeFindingKey="finding-99" activeAnchorId={null}
      density="focus" onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    ref.current?.scrollToAnnotation(annotation);
    await waitFor(() => expect(scrollPageIntoView).toHaveBeenCalledWith({ pageNumber: 99 }));
  });
});