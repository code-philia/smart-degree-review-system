import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PdfPane } from '../src/components/paperLint/PdfPane';

const api = vi.hoisted(() => ({ getDocument: vi.fn(), destroy: vi.fn(), labels: vi.fn() }));
vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({ GlobalWorkerOptions: {}, version: 'test', getDocument: api.getDocument }));
vi.mock('../src/components/paperLint/PdfViewer', async () => {
  const React = await import('react');
  return {
    preloadPdfViewer: async () => {},
    PdfViewer: React.forwardRef((props: { onReady?: () => void; onError?: (error: unknown) => void }, ref) => {
      React.useImperativeHandle(ref, () => ({ scrollToPage() {}, scrollToAnnotation() {}, currentScale: () => 1 }));
      return <div>
        <button onClick={props.onReady}>完成首屏渲染</button>
        <button onClick={() => props.onError?.(new Error('renderer module failed'))}>模拟阅读器失败</button>
      </div>;
    }),
  };
});
const pdf = { numPages: 2, getPageLabels: api.labels, destroy: async () => {} };
const props = { file: { name: 'test.pdf', url: '/api/test.pdf' }, findings: [], activeFindingKey: null,
  activeAnchorId: null, onFindingClick: vi.fn(), onAnchorClick: vi.fn(), onPageLabels: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks();
  api.labels.mockResolvedValue(null);
  api.getDocument.mockImplementation(() => ({ promise: Promise.resolve(pdf), destroy: api.destroy }));
});
afterEach(() => { vi.useRealTimers(); });

it('provides a real retry after a rejected PDF load and preserves the direct PDF fallback', async () => {
  api.getDocument.mockImplementationOnce(() => ({ promise: Promise.reject(new Error('network unavailable')), destroy: api.destroy }));
  render(<PdfPane {...props} />);
  expect(await screen.findByRole('alert')).toHaveTextContent(/PDF/);
  const retry = screen.getByRole('button', { name: '重新加载 PDF' });
  expect(screen.getByRole('link', { name: '打开完整 PDF' })).toHaveAttribute('href', '/api/test.pdf');
  fireEvent.click(retry);
  expect(await screen.findByRole('button', { name: '完成首屏渲染' })).toBeInTheDocument();
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  expect(api.destroy).toHaveBeenCalled();
});

it('stops an unresponsive loading task instead of leaving a permanent spinner', async () => {
  vi.useFakeTimers();
  api.getDocument.mockImplementation(() => ({ promise: new Promise(() => {}), destroy: api.destroy }));
  render(<PdfPane {...props} />);
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await vi.advanceTimersByTimeAsync(45_001); });
  expect(screen.getByRole('alert')).toHaveTextContent(/超时|长时间/);
  expect(screen.getByRole('button', { name: '重新加载 PDF' })).toBeEnabled();
  expect(api.destroy).toHaveBeenCalled();
});

it('waits for the first PDF paint before reading page-number metadata', async () => {
  render(<PdfPane {...props} />);
  const firstPaint = await screen.findByRole('button', { name: '完成首屏渲染' });
  expect(api.labels).not.toHaveBeenCalled();
  fireEvent.click(firstPaint);
  await waitFor(() => expect(api.labels).toHaveBeenCalled());
});

it('turns renderer initialization failures into a recoverable error', async () => {
  render(<PdfPane {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: '模拟阅读器失败' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(/PDF/);
  expect(screen.getByRole('button', { name: '重新加载 PDF' })).toBeEnabled();
});

it('does not time out an already painted PDF when later range downloads finish', async () => {
  render(<PdfPane {...props} />);
  fireEvent.click(await screen.findByRole('button', { name: '完成首屏渲染' }));
  vi.useFakeTimers();
  const task = api.getDocument.mock.results[0].value;
  act(() => task.onProgress({ loaded: 500_000, total: 1_000_000 }));
  await act(async () => { await vi.advanceTimersByTimeAsync(45_001); });
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
