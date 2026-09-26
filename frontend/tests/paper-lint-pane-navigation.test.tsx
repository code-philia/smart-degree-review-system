import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';
import { PdfPane } from '../src/components/paperLint/PdfPane';

const { scrollToAnnotation } = vi.hoisted(() => ({ scrollToAnnotation: vi.fn() }));

vi.mock('pdfjs-dist', () => ({
  GlobalWorkerOptions: {},
  getDocument: () => ({ promise: Promise.resolve({ destroy: async () => undefined }) }),
}));
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: 'test-worker' }));
vi.mock('../src/components/paperLint/PdfViewer', async () => {
  const React = await import('react');
  return {
    PdfViewer: React.forwardRef((_props: unknown, ref) => {
      React.useImperativeHandle(ref, () => ({
        scrollToAnnotation, scrollToPage: vi.fn(), currentScale: () => 1,
      }));
      return <div data-testid="loaded-pdf-viewer" />;
    }),
  };
});

const finding: PaperLintFindingItem = {
  key: 'finding-99', index: 0,
  ruleRun: { rule_run_id: 'run-24', rule_id: 'sjtu_rule_24', severity: 'warning',
    execution_status: 'completed', outcome: 'issues_found', findings: [] },
  finding: { finding_id: 'finding-99', rule_id: 'sjtu_rule_24', message: '参考文献未引用',
    location: { type: 'pdf_bbox', page_number: 99,
      bounding_rect: { x1: 85, y1: 247, x2: 517, y2: 263, width: 595, height: 842, page_number: 99 },
      rects: [] } },
};
const file = { name: 'mutant.pdf', arrayBuffer: async () => new ArrayBuffer(8) } as File;

afterEach(() => { vi.unstubAllGlobals(); scrollToAnnotation.mockClear(); });

describe('PDF pane navigation', () => {
  it('retries the selected finding after the PDF finishes loading', async () => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0);
      return 1;
    });
    render(<PdfPane file={file} findings={[finding]} activeFindingKey="finding-99"
      activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    expect(await screen.findByTestId('loaded-pdf-viewer')).toBeTruthy();
    await waitFor(() => expect(scrollToAnnotation).toHaveBeenCalledWith(
      expect.objectContaining({ pageNumber: 99 }),
    ));
  });

  it('explains the icon-only toolbar controls on hover', () => {
    render(<PdfPane file={file} findings={[]} activeFindingKey={null}
      activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()} />);
    for (const name of ['隐藏高亮', '聚焦高亮', '显示全部高亮', '缩小 PDF', '放大 PDF']) {
      expect(screen.getByRole('button', { name }).getAttribute('title')).toBe(name);
    }
  });
});