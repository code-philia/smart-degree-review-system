import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

it.each(['Escape', 'resize'] as const)('keeps the page stationary while the popup opens and closes with %s', async closeAction => {
  // jsdom has no layout: reproduce the footer sitting at the bottom of a short window.
  const geometry = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function () {
    const top = this.getAttribute('aria-label') === '每页显示条数' ? 580 : 0;
    const height = top ? 36 : 0;
    return { x: 24, y: top, left: 24, right: 136, top, bottom: top + height,
      width: 112, height, toJSON: () => ({}) };
  });
  const scrollHeight = vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(function () {
    const space = document.querySelector<HTMLElement>('section > div[aria-hidden="true"]');
    return this.hasAttribute('data-radix-select-viewport') ? 180 : 620 + (parseFloat(space?.style.height || '0') || 0);
  });
  const innerHeight = vi.spyOn(window, 'innerHeight', 'get').mockReturnValue(620);
  const position = vi.spyOn(window, 'scrollY', 'get').mockReturnValue(0);
  const scroll = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
  try {
    show();
    const trigger = screen.getByRole('combobox', { name: '每页显示条数' });
    const user = userEvent.setup();
    trigger.focus();
    await user.keyboard('{ArrowDown}');
    await screen.findByRole('listbox');
    expect(screen.getAllByRole('option')).toHaveLength(5);
    expect(scroll).not.toHaveBeenCalled();
    expect(document.documentElement.scrollHeight).toBe(620);
    if (closeAction === 'resize') fireEvent(window, new Event('resize'));
    else await user.keyboard('{Escape}');
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
    expect(scroll).not.toHaveBeenCalled();
    expect(document.documentElement.scrollHeight).toBe(620);
  } finally {
    geometry.mockRestore();
    scrollHeight.mockRestore();
    innerHeight.mockRestore();
    position.mockRestore();
    scroll.mockRestore();
  }
});
