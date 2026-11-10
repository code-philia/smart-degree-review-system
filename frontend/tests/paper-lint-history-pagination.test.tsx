import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import NormativeReportPage from '../src/pages/NormativeReportPage';
import { deletePaperLintReport, deletePaperLintReports, fetchPaperLintReports, type PaperLintReportListItem } from '../src/api/paperLint';
import { fetchNormativeDetectionHistory, fetchNormativeDetectionReport, type DetectionTaskResponse } from '../src/api/normativeRules';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: { id: 'student01' } }),
}));
vi.mock('../src/api/paperLint', async () => ({
  ...await vi.importActual('../src/api/paperLint'),
  deletePaperLintReport: vi.fn(),
  deletePaperLintReports: vi.fn(),
  fetchPaperLintReports: vi.fn(),
}));
vi.mock('../src/api/normativeRules', async () => ({
  ...await vi.importActual('../src/api/normativeRules'),
  fetchNormativeDetectionHistory: vi.fn(),
  fetchNormativeDetectionReport: vi.fn(),
}));

const reports: PaperLintReportListItem[] = Array.from({ length: 23 }, (_, index) => ({
  id: `report-${index + 1}`,
  source_filename: `论文-${String(index + 1).padStart(2, '0')}.pdf`,
  selected_rule_ids: ['sjtu_rule_22'],
  created_at: '2026-10-30T18:07:09.000Z',
  summary: {
    finding_count: index === 0 ? 0 : 12,
    error_finding_count: 0,
    warning_finding_count: index === 0 ? 0 : 12,
    info_finding_count: 0,
    rule_count: 1,
    unsupported_rule_count: 0,
    error_rule_count: 0,
    ruleset_label: '论文规范规则',
  },
}));

// jsdom does not implement pointer capture; these tests use uncaptured pointer clicks.
const needsPointerCaptureShim = !HTMLElement.prototype.hasPointerCapture;
beforeAll(() => {
  if (needsPointerCaptureShim) Object.defineProperty(HTMLElement.prototype, 'hasPointerCapture', {
    configurable: true, value: () => false,
  });
});
afterAll(() => {
  if (needsPointerCaptureShim) Reflect.deleteProperty(HTMLElement.prototype, 'hasPointerCapture');
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchPaperLintReports).mockResolvedValue(reports);
  vi.mocked(deletePaperLintReport).mockResolvedValue(undefined);
  vi.mocked(deletePaperLintReports).mockResolvedValue([]);
  vi.mocked(fetchNormativeDetectionHistory).mockResolvedValue([]);
  vi.spyOn(window, 'confirm').mockReturnValue(false);
});
afterEach(() => vi.restoreAllMocks());

async function showHistory() {
  render(<MemoryRouter><NormativeReportPage mode="thirty" /></MemoryRouter>);
  await screen.findByText('论文-01.pdf');
  await changePageSize('10');
}

async function changePageSize(value: string) {
  const user = userEvent.setup();
  await user.click(screen.getByRole('combobox', { name: '每页显示条数' }));
  await user.click(await screen.findByRole('option', { name: `${value} 条/页`, exact: true }));
}

async function manageReports() {
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: '批量管理', exact: true }));
}

async function confirmDeletion() {
  await userEvent.setup().click(within(screen.getByRole('alertdialog')).getByRole('button', { name: '确认删除', exact: true }));
}

async function deleteReport(filename: string) {
  const user = userEvent.setup();
  const row = screen.getByRole('link', { name: filename, exact: true }).closest('tr')!;
  await user.click(within(row).getByRole('button', { name: '删除报告', exact: true }));
  await confirmDeletion();
}

function shownRows() {
  return within(screen.getByRole('table', { name: '规范性检测报告' })).getAllByRole('row').slice(1);
}

it('shows the required report columns, numeric results, seconds and existing detail routes', async () => {
  await showHistory();
  const table = screen.getByRole('table', { name: '规范性检测报告' });
  for (const name of ['文档名称', '检测类型', '检测结果', '报告生成时间', '操作']) {
    expect(within(table).getByRole('columnheader', { name })).toBeInTheDocument();
  }
  const first = shownRows()[0];
  expect(within(first).getByText('规范性检测')).toBeInTheDocument();
  expect(within(first).getByText('错误总数：0')).toBeInTheDocument();
  expect(within(first).getByText('2026-10-31 02:07:09')).toBeInTheDocument();
  expect(within(first).getByRole('link', { name: '查看详情' })).toHaveAttribute('href', '/reports/pdf/report-1');
  expect(within(shownRows()[1]).getByText('错误总数：12')).toBeInTheDocument();
});

it('paginates actual rows and resets to the first page after the page size changes', async () => {
  await showHistory();
  expect(shownRows()).toHaveLength(10);
  expect(screen.queryByText('论文-11.pdf')).not.toBeInTheDocument();
  expect(screen.getByText('第 1 / 3 页')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  expect(screen.getByText('论文-11.pdf')).toBeInTheDocument();
  expect(screen.queryByText('论文-01.pdf')).not.toBeInTheDocument();

  const pageSize = screen.getByRole('combobox', { name: '每页显示条数' });
  const user = userEvent.setup();
  await user.click(pageSize);
  expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['5 条/页', '10 条/页', '20 条/页', '50 条/页', '100 条/页']);
  expect(screen.getByRole('option', { name: '10 条/页', exact: true })).toHaveAttribute('aria-selected', 'true');
  await user.click(screen.getByRole('option', { name: '20 条/页', exact: true }));
  expect(shownRows()).toHaveLength(20);
  expect(screen.getByText('第 1 / 2 页')).toBeInTheDocument();
  expect(screen.getByText('论文-01.pdf')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  expect(shownRows()).toHaveLength(3);
  expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
  await changePageSize('50');
  expect(shownRows()).toHaveLength(23);
  expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument();
});

it('preserves selection across pages and selects or clears only the current page', async () => {
  await showHistory();
  await manageReports();
  fireEvent.click(screen.getByRole('checkbox', { name: '选择报告：论文-01.pdf' }));
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  const selectPage = screen.getByRole('checkbox', { name: '全选报告' });
  expect(screen.getByText('全选本页')).toBeInTheDocument();
  expect(selectPage).not.toBeChecked();
  fireEvent.click(selectPage);
  expect(screen.getByRole('button', { name: '删除选中（11）' })).toBeEnabled();
  fireEvent.click(selectPage);
  expect(screen.getByRole('button', { name: '删除选中（1）' })).toBeEnabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '选择报告：论文-11.pdf' }));
  fireEvent.click(screen.getByRole('button', { name: '上一页' }));
  expect(screen.getByRole('checkbox', { name: '选择报告：论文-01.pdf' })).toBeChecked();
  fireEvent.click(screen.getByRole('button', { name: '删除选中（2）' }));
  await confirmDeletion();
  await waitFor(() => expect(screen.queryByText('论文-01.pdf')).not.toBeInTheDocument());
  expect(deletePaperLintReports).toHaveBeenCalledWith(['report-1', 'report-11']);
  expect(window.confirm).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  expect(screen.queryByText('论文-11.pdf')).not.toBeInTheDocument();
});

it('clamps the page after deleting the final page and preserves records when a batch is cancelled or fails', async () => {
  await showHistory();
  await manageReports();
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  fireEvent.click(screen.getByRole('checkbox', { name: '全选报告' }));
  fireEvent.click(screen.getByRole('button', { name: '删除选中（3）' }));
  await userEvent.setup().click(within(screen.getByRole('alertdialog')).getByRole('button', { name: '取消', exact: true }));
  expect(deletePaperLintReports).not.toHaveBeenCalled();
  expect(screen.getByText('论文-23.pdf')).toBeInTheDocument();
  vi.mocked(deletePaperLintReports).mockRejectedValueOnce(new Error('批量删除未完成'));
  fireEvent.click(screen.getByRole('button', { name: '删除选中（3）' }));
  await confirmDeletion();
  expect(await screen.findByText('批量删除未完成')).toBeInTheDocument();
  expect(screen.getByText('论文-23.pdf')).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: '选择报告：论文-23.pdf', hidden: true })).toBeChecked();
  await confirmDeletion();
  await waitFor(() => expect(screen.getByText('第 2 / 2 页')).toBeInTheDocument());
  expect(shownRows()).toHaveLength(10);
  expect(screen.getByText('论文-11.pdf')).toBeInTheDocument();
  expect(screen.queryByText('论文-23.pdf')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
  await deleteReport('论文-11.pdf');
  await waitFor(() => expect(screen.queryByText('论文-11.pdf')).not.toBeInTheDocument());
  expect(shownRows()).toHaveLength(9);
  expect(deletePaperLintReport).toHaveBeenCalledWith('report-11');
});

it('preserves the legacy text history and its existing detail branch alongside PDF history', async () => {
  const legacyReport: DetectionTaskResponse = {
    id: 'text-report',
    user_id: 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: '文本论文.txt',
    original_text: '文本报告正文',
    rule_snapshot: [],
    issues: [],
    severity_counts: { high: 0, medium: 0, low: 0 },
    created_at: '2026-10-30T18:07:09.000Z',
  };
  vi.mocked(fetchNormativeDetectionHistory).mockResolvedValue([legacyReport]);
  vi.mocked(fetchNormativeDetectionReport).mockResolvedValue(legacyReport);
  render(
    <MemoryRouter initialEntries={['/normative-reports']}>
      <Routes>
        <Route path="/normative-reports" element={<NormativeReportPage />} />
        <Route path="/normative-reports/:reportId" element={<NormativeReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText('文本规范检测记录')).toBeInTheDocument();
  const preview = screen.getByRole('link', { name: '报告预览' });
  expect(preview).toHaveAttribute('href', '/normative-reports/text-report');
  expect(screen.getByText('2026-10-31 02:07')).toBeInTheDocument();
  expect(within(shownRows()[0]).getByRole('link', { name: '查看详情' })).toHaveAttribute('href', '/normative-reports/pdf/report-1');
  fireEvent.click(preview);
  expect(await screen.findByText('文本报告正文')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '检测报告' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '下载 UTF-8 JSON' })).toBeInTheDocument();
});
