import { useState } from 'react';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { ReportHistoryTable } from '../src/components/paperLint/ReportHistoryTable';
import type { PaperLintReportListItem } from '../src/api/paperLint';

const filenames = [
  '前言.pdf', 'Survey.pdf', '研究记录.pdf', 'appendix.pdf', '摘要.pdf',
  'THESIS-01.pdf', 'thesis-02.pdf', 'Thesis-03.pdf', 'thesis-04.pdf',
  'THESIS-05.pdf', 'thesis-06.pdf', 'Thesis-07.pdf', '附录.pdf',
];
const reports: PaperLintReportListItem[] = filenames.map((source_filename, index) => ({
  id: `report-${index + 1}`,
  source_filename,
  selected_rule_ids: ['sjtu_rule_22'],
  created_at: '2026-10-31T01:02:03Z',
  summary: {
    finding_count: index,
    error_finding_count: 0,
    warning_finding_count: index,
    info_finding_count: 0,
    rule_count: 1,
    unsupported_rule_count: 0,
    error_rule_count: 0,
    ruleset_label: '当前规则',
  },
}));

function show(savedReports = reports) {
  const onDelete = vi.fn();
  function History() {
    const [selected, setSelected] = useState<string[]>([]);
    return <ReportHistoryTable reports={savedReports} historyPath="/reports"
      selectedReportIds={selected} onSelectionChange={setSelected} deleting={false} onDelete={onDelete} />;
  }
  render(<MemoryRouter><History /></MemoryRouter>);
  return { user: userEvent.setup(), onDelete };
}

function rowNames() {
  return within(screen.getByRole('table', { name: 'PDF 论文检查报告' }))
    .getAllByRole('link', { name: '查看详情' })
    .map(link => within(link.closest('tr')!).getByTitle(/\.pdf$/).textContent);
}

it('searches every saved filename with a trimmed case-insensitive substring before paginating', () => {
  show();
  expect(rowNames()).toEqual(['前言.pdf', 'Survey.pdf', '研究记录.pdf', 'appendix.pdf', '摘要.pdf']);
  const search = screen.getByRole('searchbox', { name: '搜索检测报告' });
  expect(search).toHaveAttribute('placeholder', '搜索文档名称…');
  fireEvent.change(search, { target: { value: '  tHeSiS-  ' } });
  expect(rowNames()).toEqual(['THESIS-01.pdf', 'thesis-02.pdf', 'Thesis-03.pdf', 'thesis-04.pdf', 'THESIS-05.pdf']);
  expect(screen.getByText('13 份')).toBeInTheDocument();
  expect(screen.getByText('匹配 7 份')).toBeInTheDocument();
  const pagination = screen.getByRole('navigation', { name: '报告分页' });
  expect(within(pagination).getByText('共 13 条，匹配 7 条，显示第 1–5 条')).toBeInTheDocument();
  fireEvent.click(within(pagination).getByRole('button', { name: '下一页' }));
  expect(rowNames()).toEqual(['thesis-06.pdf', 'Thesis-07.pdf']);
  expect(within(pagination).getByText('第 2 / 2 页')).toBeInTheDocument();
});

it('resets the page for a changed query and restores the full first page when cleared', () => {
  show();
  const search = screen.getByRole('searchbox', { name: '搜索检测报告' });
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  fireEvent.change(search, { target: { value: 'thesis-' } });
  expect(rowNames()[0]).toBe('THESIS-01.pdf');
  fireEvent.click(screen.getByRole('button', { name: '下一页' }));
  fireEvent.change(search, { target: { value: 'Thesis-03' } });
  expect(rowNames()).toEqual(['Thesis-03.pdf']);
  expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '清空搜索' }));
  expect(search).toHaveValue('');
  expect(rowNames()).toEqual(['前言.pdf', 'Survey.pdf', '研究记录.pdf', 'appendix.pdf', '摘要.pdf']);
  expect(screen.getByText('第 1 / 3 页')).toBeInTheDocument();
  expect(screen.queryByText(/匹配 \d+ 份/)).not.toBeInTheDocument();
});

it('shows a safe zero-result state and lets the user restore all reports', () => {
  show();
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索检测报告' }), { target: { value: '不存在' } });
  expect(screen.getByText('未找到匹配的报告')).toBeInTheDocument();
  expect(screen.getByText('匹配 0 份')).toBeInTheDocument();
  expect(screen.getByText('共 13 条，匹配 0 条，显示第 0–0 条')).toBeInTheDocument();
  expect(screen.queryByRole('link', { name: '查看详情' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '上一页' })).toBeDisabled();
  expect(screen.getByRole('button', { name: '下一页' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: '查看全部报告' }));
  expect(screen.getByRole('searchbox', { name: '搜索检测报告' })).toHaveValue('');
  expect(rowNames()).toHaveLength(5);
});

it('clears existing selections whenever the search changes so hidden reports cannot be batch deleted', async () => {
  const { user, onDelete } = show();
  await user.click(screen.getByRole('button', { name: '报告管理' }));
  await user.click(screen.getByRole('menuitem', { name: '批量管理' }));
  fireEvent.click(screen.getByRole('checkbox', { name: '选择报告：前言.pdf' }));
  expect(screen.getByRole('button', { name: '删除选中（1）' })).toBeEnabled();
  const search = screen.getByRole('searchbox', { name: '搜索检测报告' });
  fireEvent.change(search, { target: { value: 'thesis-' } });
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '选择报告：THESIS-01.pdf' }));
  fireEvent.change(search, { target: { value: 'thesis-02' } });
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox', { name: '全选报告' }));
  fireEvent.click(screen.getByRole('button', { name: '删除选中（1）' }));
  expect(onDelete).toHaveBeenCalledExactlyOnceWith(['report-7'], true);
  fireEvent.click(screen.getByRole('button', { name: '清空搜索' }));
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
  expect(screen.getByRole('checkbox', { name: '选择报告：前言.pdf' })).not.toBeChecked();
});

it('treats whitespace as an unfiltered query and renders a valid range for an empty saved list', () => {
  show([]);
  fireEvent.change(screen.getByRole('searchbox', { name: '搜索检测报告' }), { target: { value: '   ' } });
  expect(screen.getByText('共 0 条，显示第 0–0 条')).toBeInTheDocument();
  expect(screen.queryByText(/匹配 \d+ 份/)).not.toBeInTheDocument();
  expect(screen.getByText('第 1 / 1 页')).toBeInTheDocument();
});
