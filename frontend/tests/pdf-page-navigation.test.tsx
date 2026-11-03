import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PdfPane } from '../src/components/paperLint/PdfPane';
import { LivePaperLintReport } from '../src/components/paperLint/LivePaperLintReport';
import type { PaperLintFindingItem } from '../src/components/paperLint/model';

const api = vi.hoisted(() => ({
  getDocument: vi.fn(), scrollToPage: vi.fn(), scrollToAnnotation: vi.fn(),
  pageChanged: undefined as ((page: number) => void) | undefined,
}));
vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({
  GlobalWorkerOptions: {}, version: 'test', getDocument: api.getDocument,
}));
vi.mock('../src/components/paperLint/PdfViewer', async () => {
  const React = await import('react');
  return { preloadPdfViewer: async () => {}, PdfViewer: React.forwardRef((props: {
    onReady?: () => void; onPageChange?: (page: number) => void;
  }, ref) => {
    api.pageChanged = props.onPageChange;
    React.useImperativeHandle(ref, () => ({
      scrollToPage: api.scrollToPage, scrollToAnnotation: api.scrollToAnnotation, currentScale: () => 1,
    }));
    React.useEffect(() => { props.onReady?.(); }, [props.onReady]);
    return <div data-testid="test-reader" />;
  }) };
});

const pdf = { numPages: 120, getPageLabels: async () => null };
const props = { file: { name: 'paper.pdf', url: '/paper.pdf' }, findings: [], activeFindingKey: null,
  activeAnchorId: null, onFindingClick: vi.fn(), onAnchorClick: vi.fn() };
beforeEach(() => {
  vi.clearAllMocks(); api.pageChanged = undefined;
  api.getDocument.mockImplementation(() => ({ promise: Promise.resolve(pdf), destroy: vi.fn() }));
});
afterEach(() => vi.unstubAllGlobals());
function expandToolbar() {
  const toggle = screen.queryByRole('button', { name: '展开阅读工具' });
  if (toggle) fireEvent.click(toggle);
}
async function loaded() {
  expandToolbar();
  const input = await screen.findByRole('textbox', { name: 'PDF 页码' });
  await waitFor(() => expect(input).toBeEnabled());
  return input;
}

it.each(['saved', 'live'])('starts the %s toolbar collapsed and preserves the PDF and page when toggled', async kind => {
  const user = userEvent.setup();
  render(kind === 'live'
    ? <LivePaperLintReport file={props.file} rules={[]} runs={[]} />
    : <PdfPane {...props} />);
  await screen.findByTestId('test-reader');
  const expand = screen.getByRole('button', { name: '展开阅读工具' });
  expect(expand).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('form', { name: 'PDF 页码跳转' })).not.toBeInTheDocument();
  expect(screen.queryByRole('toolbar', { name: 'PDF 工具' })).not.toBeInTheDocument();

  await user.click(expand);
  const input = await loaded();
  const collapse = screen.getByRole('button', { name: '收起阅读工具' });
  expect(collapse).toHaveAttribute('aria-expanded', 'true');
  expect(document.getElementById(collapse.getAttribute('aria-controls')!)).toBeVisible();
  await user.clear(input); await user.type(input, '87{Enter}');
  expect(input).toHaveValue('87');
  const reader = screen.getByTestId('test-reader');
  await user.click(collapse);
  expect(screen.queryByRole('textbox', { name: 'PDF 页码' })).not.toBeInTheDocument();
  expect(screen.getByTestId('test-reader')).toBe(reader);
  expect(screen.getByRole('button', { name: '展开阅读工具' })).toHaveFocus();
  await user.click(screen.getByRole('button', { name: '展开阅读工具' }));
  expect(screen.getByRole('textbox', { name: 'PDF 页码' })).toHaveValue('87');
  expect(screen.getByRole('link', { name: '在浏览器打开完整 PDF' })).toHaveAttribute('href', '/paper.pdf#page=87');
  expect(api.getDocument).toHaveBeenCalledTimes(1);
});

it('jumps by Enter without any findings and displays the loaded page count', async () => {
  const user = userEvent.setup();
  render(<PdfPane {...props} />);
  const input = await loaded();
  expect(input).toHaveValue('1');
  expect(screen.getByTitle('PDF 总页数')).toHaveTextContent('120');
  expect(screen.getByRole('button', { name: 'PDF 上一页' })).toBeDisabled();
  await user.clear(input); await user.type(input, '87');
  expect(api.scrollToPage).not.toHaveBeenCalled();
  await user.keyboard('{Enter}');
  expect(api.scrollToPage).toHaveBeenCalledWith(87);
  expect(screen.getByRole('link', { name: '在浏览器打开完整 PDF' })).toHaveAttribute('href', '/paper.pdf#page=87');
  await user.keyboard('{Enter}');
  expect(api.scrollToPage).toHaveBeenCalledTimes(2);
});

it.each(['', '0', '121', '-1', '1.5', '1e2', 'abc'])('does not navigate invalid page input %j', async value => {
  render(<PdfPane {...props} />);
  const input = await loaded();
  fireEvent.change(input, { target: { value } });
  fireEvent.submit(screen.getByRole('form', { name: 'PDF 页码跳转' }));
  expect(api.scrollToPage).not.toHaveBeenCalled();
  expect(input).toHaveAttribute('aria-invalid', 'true');
  expect(screen.getByRole('alert')).toHaveTextContent(/1.*120.*整数/);
});

it('follows actual reader pages and respects first/last page bounds', async () => {
  render(<PdfPane {...props} />);
  const input = await loaded();
  act(() => api.pageChanged?.(42));
  expect(input).toHaveValue('42');
  fireEvent.click(screen.getByRole('button', { name: 'PDF 上一页' }));
  expect(api.scrollToPage).toHaveBeenLastCalledWith(41);
  fireEvent.click(screen.getByRole('button', { name: 'PDF 下一页' }));
  expect(api.scrollToPage).toHaveBeenLastCalledWith(42);
  act(() => api.pageChanged?.(120));
  expect(input).toHaveValue('120');
  expect(screen.getByRole('button', { name: 'PDF 下一页' })).toBeDisabled();
});

it('preserves the typed draft during reader updates and normalizes it on submit', async () => {
  render(<PdfPane {...props} />);
  const input = await loaded();
  fireEvent.change(input, { target: { value: ' 0087 ' } });
  act(() => api.pageChanged?.(42));
  expect(input).toHaveValue(' 0087 ');
  fireEvent.submit(screen.getByRole('form', { name: 'PDF 页码跳转' }));
  expect(api.scrollToPage).toHaveBeenLastCalledWith(87);
  expect(input).toHaveValue('87');
});

it('keeps controls disabled while the PDF is loading', () => {
  api.getDocument.mockReturnValue({ promise: new Promise(() => {}), destroy: vi.fn() });
  render(<PdfPane {...props} />);
  expandToolbar();
  expect(screen.getByRole('textbox', { name: 'PDF 页码' })).toBeDisabled();
  for (const name of ['PDF 上一页', 'PDF 下一页']) {
    expect(screen.getByRole('button', { name })).toBeDisabled();
  }
});

it('disables page navigation after a PDF load fails', async () => {
  api.getDocument.mockReturnValue({ promise: Promise.reject(new Error('Invalid PDF')), destroy: vi.fn() });
  render(<PdfPane {...props} />);
  await screen.findByRole('alert');
  expandToolbar();
  expect(screen.getByRole('textbox', { name: 'PDF 页码' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'PDF 下一页' })).toBeDisabled();
  expect(api.scrollToPage).not.toHaveBeenCalled();
});

it('resets to page one with new bounds when the PDF changes', async () => {
  const { rerender } = render(<PdfPane {...props} />);
  const input = await loaded();
  fireEvent.change(input, { target: { value: '120' } });
  fireEvent.submit(screen.getByRole('form', { name: 'PDF 页码跳转' }));
  api.getDocument.mockImplementation(() => ({ promise: Promise.resolve({ ...pdf, numPages: 3 }), destroy: vi.fn() }));
  rerender(<PdfPane {...props} file={{ name: 'replacement.pdf', url: '/replacement.pdf' }} />);
  await waitFor(() => expect(screen.getByTitle('PDF 总页数')).toHaveTextContent('3'));
  expect(await loaded()).toHaveValue('1');
  api.scrollToPage.mockClear();
  fireEvent.change(input, { target: { value: '4' } });
  fireEvent.submit(screen.getByRole('form', { name: 'PDF 页码跳转' }));
  expect(api.scrollToPage).not.toHaveBeenCalled();
});

it('preserves a manual page jump during live finding refresh and still honors finding navigation', async () => {
  const finding = { key: 'f', index: 0, finding: { finding_id: 'f', rule_id: 'rule', message: 'Issue',
    location: { type: 'pdf_page', page_number: 9 } }, ruleRun: { rule_id: 'rule', findings: [] } } as PaperLintFindingItem;
  const { rerender } = render(<PdfPane {...props} findings={[finding]} activeFindingKey="f" />);
  const input = await loaded();
  await waitFor(() => expect(api.scrollToPage).toHaveBeenCalledWith(9));
  fireEvent.change(input, { target: { value: '87' } });
  fireEvent.submit(screen.getByRole('form', { name: 'PDF 页码跳转' }));
  api.scrollToPage.mockClear();
  rerender(<PdfPane {...props} findings={[{ ...finding, finding: { ...finding.finding, message: 'Updated issue' } }]} activeFindingKey="f" />);
  expect(api.scrollToPage).not.toHaveBeenCalled();
  expect(input).toHaveValue('87');
  rerender(<PdfPane {...props} findings={[finding]} activeFindingKey="f" navigationRequest={1} />);
  await waitFor(() => expect(api.scrollToPage).toHaveBeenLastCalledWith(9));
});

it('opens an uploaded PDF from the live report and keeps its URL valid across finding updates', async () => {
  const create = vi.fn().mockReturnValueOnce('blob:live-first').mockReturnValueOnce('blob:live-next');
  const revoke = vi.fn();
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = create;
    static revokeObjectURL = revoke;
  });
  const upload = (name: string) => Object.assign(new File(['pdf'], name, { type: 'application/pdf' }), {
    arrayBuffer: async () => new ArrayBuffer(3),
  });
  const first = upload('first.pdf');
  const { rerender, unmount } = render(<LivePaperLintReport file={first} rules={[]} runs={[]} />);
  await loaded();
  const link = await screen.findByRole('link', { name: '在浏览器打开完整 PDF' });
  expect(link).toHaveAttribute('href', 'blob:live-first#page=1');
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  const input = screen.getByRole('textbox', { name: 'PDF 页码' });
  fireEvent.change(input, { target: { value: '87' } });
  fireEvent.submit(screen.getByRole('form', { name: 'PDF 页码跳转' }));
  rerender(<LivePaperLintReport file={first} rules={[]} runs={[]} />);
  expect(link).toHaveAttribute('href', 'blob:live-first#page=87');
  expect(create).toHaveBeenCalledTimes(1);
  expect(revoke).not.toHaveBeenCalled();

  rerender(<LivePaperLintReport file={upload('replacement.pdf')} rules={[]} runs={[]} />);
  await waitFor(() => expect(screen.getByRole('link', { name: '在浏览器打开完整 PDF' })).toHaveAttribute('href', 'blob:live-next#page=1'));
  expect(revoke).toHaveBeenCalledWith('blob:live-first');
  expect(revoke).not.toHaveBeenCalledWith('blob:live-next');
  unmount();
  expect(revoke).toHaveBeenCalledWith('blob:live-next');
});
