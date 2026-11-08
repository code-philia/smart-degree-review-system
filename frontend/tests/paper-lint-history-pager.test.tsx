import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { ReportHistoryTable } from '../src/components/paperLint/ReportHistoryTable';
import type { PaperLintReportListItem } from '../src/api/paperLint';

const reports: PaperLintReportListItem[] = Array.from({ length: 143 }, (_, index) => ({
  id: String(index + 1), source_filename: `论文-${index + 1}.pdf`,
  selected_rule_ids: ['sjtu_rule_22'], created_at: '2026-11-08T08:00:00Z',
  summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0,
    info_finding_count: 0, rule_count: 1, unsupported_rule_count: 0, error_rule_count: 0, ruleset_label: '' },
}));
function show(savedReports = reports, deleting = false) {
  render(<MemoryRouter><ReportHistoryTable reports={savedReports} historyPath="/reports"
    selectedReportIds={[]} onSelectionChange={vi.fn()} deleting={deleting} onDelete={vi.fn()} /></MemoryRouter>);
  return within(screen.getByRole('navigation', { name: '报告分页' }));
}
function jump(value: string, event: 'enter' | 'blur' = 'enter') {
  const input = screen.getByRole('textbox', { name: '跳转页码' });
  fireEvent.change(input, { target: { value } });
  if (event === 'enter') fireEvent.keyDown(input, { key: 'Enter' });
  else fireEvent.blur(input);
}
it('opens numbered pages and announces the selected page while bounding a long pager', () => {
  const nav = show();
  expect(nav.getByRole('button', { name: '第 1 页', exact: true })).toHaveAttribute('aria-current', 'page');
  fireEvent.click(nav.getByRole('button', { name: '第 3 页', exact: true }));
  expect(screen.getByRole('link', { name: '论文-11.pdf', exact: true })).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: '论文-1.pdf', exact: true })).not.toBeInTheDocument();
  expect(nav.getByRole('button', { name: '第 3 页', exact: true })).toHaveAttribute('aria-current', 'page');
  jump('15');
  expect(screen.getByRole('link', { name: '论文-71.pdf', exact: true })).toBeInTheDocument();
  expect(nav.getByRole('button', { name: '第 15 页', exact: true })).toHaveAttribute('aria-current', 'page');
  expect(nav.getByRole('button', { name: '第 1 页', exact: true })).toBeInTheDocument();
  expect(nav.getByRole('button', { name: '第 29 页', exact: true })).toBeInTheDocument();
  expect(nav.getAllByRole('button').length).toBeLessThanOrEqual(7);
  fireEvent.click(nav.getByRole('button', { name: '第 29 页', exact: true }));
  expect(screen.getByRole('link', { name: '论文-141.pdf', exact: true })).toBeInTheDocument();
  expect(nav.getByRole('button', { name: '下一页', exact: true })).toBeDisabled();
});
it('jumps on Enter or blur, clamps whole page numbers and rejects blank or malformed input', () => {
  show();
  jump('12');
  expect(screen.getByText('第 12 / 29 页')).toBeInTheDocument();
  jump('999', 'blur');
  expect(screen.getByText('第 29 / 29 页')).toBeInTheDocument();
  for (const value of ['', 'abc', '1.5', '-2', '1e2', '999999999999999999999']) {
    jump(value);
    expect(screen.getByText('第 29 / 29 页')).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: '跳转页码' })).toHaveValue('29');
  }
  jump('0');
  expect(screen.getByText('第 1 / 29 页')).toBeInTheDocument();
  jump(' 2 ', 'blur');
  expect(screen.getByText('第 2 / 29 页')).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索检测报告' }), { target: { value: '论文-143.pdf' } });
  expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: '跳转页码' })).toBeDisabled();
});
it('disables every page control while deleting and handles empty or single-page results', () => {
  const nav = show(reports, true);
  expect(nav.getByRole('combobox', { name: '每页显示条数' })).toBeDisabled();
  expect(nav.getByRole('textbox', { name: '跳转页码' })).toBeDisabled();
  for (const button of nav.getAllByRole('button')) expect(button).toBeDisabled();
});
it('keeps empty pagination bounded at page one', () => {
  const nav = show([]);
  expect(screen.getByText('共 0 条，显示第 0–0 条')).toBeInTheDocument();
  expect(nav.getByRole('button', { name: '上一页' })).toBeDisabled();
  expect(nav.getByRole('button', { name: '下一页' })).toBeDisabled();
  expect(nav.getByRole('textbox', { name: '跳转页码' })).toBeDisabled();
  expect(nav.getByRole('button', { name: '第 1 页', exact: true })).toHaveAttribute('aria-current', 'page');
});

it('preserves keyboard focus after submitting a different page', () => {
  show();
  const input = screen.getByRole('textbox', { name: '跳转页码' });
  input.focus();
  fireEvent.change(input, { target: { value: '2' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(screen.getByText('第 2 / 29 页')).toBeInTheDocument();
  expect(screen.getByRole('textbox', { name: '跳转页码' })).toHaveFocus();
});
