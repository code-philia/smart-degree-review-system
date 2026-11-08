import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { ReportHistoryTable } from '../src/components/paperLint/ReportHistoryTable';
import type { PaperLintReportListItem } from '../src/api/paperLint';

const reports: PaperLintReportListItem[] = [{ id: 'example', source_filename: '示例论文.pdf', selected_rule_ids: ['sjtu_rule_22'],
  created_at: '2026-10-31T01:02:03Z', summary: { finding_count: 8, error_finding_count: 2, warning_finding_count: 6,
    info_finding_count: 0, rule_count: 1, unsupported_rule_count: 0, error_rule_count: 0, ruleset_label: '当前规则' } }];
function show(onDelete = vi.fn()) {
  function History() {
    const [selected, setSelected] = useState<string[]>([]);
    return <ReportHistoryTable reports={reports} historyPath="/reports" selectedReportIds={selected}
      onSelectionChange={setSelected} deleting={false} onDelete={onDelete} />;
  }
  render(<MemoryRouter><History /></MemoryRouter>);
  return { user: userEvent.setup(), onDelete };
}

it('shows the required fields and all report actions directly', () => {
  show();
  const table = screen.getByRole('table', { name: 'PDF 论文检查报告' });
  expect(within(table).getAllByRole('columnheader').map(header => header.textContent)).toEqual(['文档名称','检测类型','检测结果','报告生成时间','操作']);
  expect(screen.getByText('错误总数：8')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '查看详情' })).toHaveAttribute('href','/reports/pdf/example');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '删除报告', exact: true })).toBeEnabled();
  expect(screen.getByRole('link', { name: '增量补跑', exact: true })).toHaveAttribute('href', '/reports/pdf/example?rerun=1');
  expect(screen.getByRole('button', { name: '批量管理', exact: true })).toBeEnabled();
  expect(screen.queryByRole('button', { name: /更多操作|报告管理/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: /删除/ })).not.toBeInTheDocument();
});

it('opens the same report from its filename and detail action with a safe encoded identifier', () => {
  render(<MemoryRouter><ReportHistoryTable reports={[{ ...reports[0], id: 'example/论文 #1' }]}
    historyPath="/reports" selectedReportIds={[]} onSelectionChange={vi.fn()}
    deleting={false} onDelete={vi.fn()} /></MemoryRouter>);
  expect(screen.getByRole('link', { name: '示例论文.pdf' }))
    .toHaveAttribute('href', '/reports/pdf/example%2F%E8%AE%BA%E6%96%87%20%231');
  expect(screen.getByRole('link', { name: '查看详情' }))
    .toHaveAttribute('href', '/reports/pdf/example%2F%E8%AE%BA%E6%96%87%20%231');
});

it('calls the existing deletion handler from the visible row action', async () => {
  const { user, onDelete } = show();
  expect(onDelete).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button', { name: '删除报告', exact: true }));
  expect(onDelete).toHaveBeenCalledExactlyOnceWith(['example']);
});

it('opens batch management directly and clears selection when management is closed', async () => {
  const { user, onDelete } = show();
  async function manage() {
    await user.click(screen.getByRole('button', { name: '批量管理', exact: true }));
  }
  await manage();
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
  await user.click(screen.getByRole('checkbox', { name: '全选报告' }));
  expect(screen.getByRole('button', { name: '删除选中（1）' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: '完成管理' }));
  expect(screen.getByRole('button', { name: '批量管理', exact: true })).toHaveFocus();
  expect(onDelete).not.toHaveBeenCalled();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /删除选中/ })).not.toBeInTheDocument();
  await manage();
  expect(screen.getByRole('checkbox', { name: '全选报告' })).not.toBeChecked();
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
});

it('disables management, reruns and deletion while a deletion is pending', () => {
  const onDelete = vi.fn();
  render(<MemoryRouter><ReportHistoryTable reports={reports} historyPath="/reports" selectedReportIds={[]}
    onSelectionChange={vi.fn()} deleting onDelete={onDelete} /></MemoryRouter>);
  expect(screen.getByRole('button', { name: '批量管理', exact: true })).toBeDisabled();
  expect(screen.getByRole('button', { name: '删除报告', exact: true })).toBeDisabled();
  expect(screen.getByRole('link', { name: '增量补跑', exact: true })).toHaveAttribute('aria-disabled', 'true');
  expect(onDelete).not.toHaveBeenCalled();
});
