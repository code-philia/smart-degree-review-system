import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ReportExportDialog } from '../src/components/paperLint/ReportExportDialog';
import { fetchPaperLintRepairSuggestionHistory } from '../src/api/repairSuggestions';
import { createReportFile, downloadReportFile } from '../src/utils/reportExport/formats';
import { fixture } from './fixtures/reportExport';

vi.mock('../src/api/repairSuggestions', () => ({ fetchPaperLintRepairSuggestionHistory: vi.fn() }));
vi.mock('../src/utils/reportExport/formats', () => ({ createReportFile: vi.fn(), downloadReportFile: vi.fn() }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchPaperLintRepairSuggestionHistory).mockResolvedValue([]);
  vi.mocked(createReportFile).mockResolvedValue({ filename: '检测报告.pdf', blob: new Blob(['report']) });
});
it('offers all six formats and exports only saved data without triggering a detector', async () => {
  const user = userEvent.setup();
  render(<ReportExportDialog report={fixture} rules={[]} metrics={null} />);
  await user.click(screen.getByRole('button', { name: '下载检测报告' }));
  for (const [label, format] of [
    ['PDF', 'pdf'],
    ['Markdown', 'markdown'],
    ['文本', 'text'],
    ['Word / DOCX', 'docx'],
    ['图片 / PNG', 'image'],
    ['JSON', 'json'],
  ]) {
    await user.click(screen.getByRole('button', { name: `导出 ${label}` }));
    await waitFor(() =>
      expect(createReportFile).toHaveBeenLastCalledWith(
        expect.objectContaining({ report_id: fixture.id }),
        format,
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ),
    );
    await waitFor(() =>
      expect(downloadReportFile).toHaveBeenCalledTimes(
        ['pdf', 'markdown', 'text', 'docx', 'image', 'json'].indexOf(format) + 1,
      ),
    );
  }
  expect(fetchPaperLintRepairSuggestionHistory).toHaveBeenCalledWith(fixture.id);
});
it('prevents duplicate exports and supports retry after a saved-suggestion read failure', async () => {
  let reject!: (reason: Error) => void;
  vi.mocked(fetchPaperLintRepairSuggestionHistory).mockReturnValueOnce(
    new Promise((_, fail) => {
      reject = fail;
    }),
  );
  const user = userEvent.setup();
  render(<ReportExportDialog report={fixture} rules={[]} metrics={null} />);
  await user.click(screen.getByRole('button', { name: '下载检测报告' }));
  const button = screen.getByRole('button', { name: '导出 PDF' });
  await user.dblClick(button);
  expect(fetchPaperLintRepairSuggestionHistory).toHaveBeenCalledTimes(1);
  expect(button).toBeDisabled();
  reject(new Error('读取已保存建议失败'));
  expect(await screen.findByRole('alert')).toHaveTextContent('读取已保存建议失败');
  await user.click(button);
  await waitFor(() => expect(downloadReportFile).toHaveBeenCalledTimes(1));
});
it('does not download a report after the view unmounts', async () => {
  let resolve!: (value: []) => void;
  vi.mocked(fetchPaperLintRepairSuggestionHistory).mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const view = render(<ReportExportDialog report={fixture} rules={[]} metrics={null} />);
  fireEvent.click(screen.getByRole('button', { name: '下载检测报告' }));
  fireEvent.click(screen.getByRole('button', { name: '导出 JSON' }));
  view.unmount();
  resolve([]);
  await Promise.resolve();
  expect(downloadReportFile).not.toHaveBeenCalled();
});
it('cancels a pending export without downloading and allows a fresh attempt', async () => {
  let resolve!: (value: []) => void;
  vi.mocked(fetchPaperLintRepairSuggestionHistory).mockReturnValueOnce(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const user = userEvent.setup();
  render(<ReportExportDialog report={fixture} rules={[]} metrics={null} />);
  await user.click(screen.getByRole('button', { name: '下载检测报告' }));
  await user.click(screen.getByRole('button', { name: '导出 PDF' }));
  await user.click(screen.getByRole('button', { name: '取消导出' }));
  resolve([]);
  await waitFor(() => expect(screen.getByRole('button', { name: '导出 PDF' })).toBeEnabled());
  expect(downloadReportFile).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: '导出 JSON' }));
  await waitFor(() => expect(downloadReportFile).toHaveBeenCalledTimes(1));
});
