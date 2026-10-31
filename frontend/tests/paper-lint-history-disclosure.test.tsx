import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
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
    return <ReportHistoryTable reports={reports} historyPath="/thirty-rules-check/reports" selectedReportIds={selected}
      onSelectionChange={setSelected} deleting={false} onDelete={onDelete} />;
  }
  render(<MemoryRouter><History /></MemoryRouter>);
  return { user: userEvent.setup(), onDelete };
}

it('keeps all required fields and detail navigation without exposing deletion controls', () => {
  show();
  const table = screen.getByRole('table', { name: 'PDF 论文检查报告' });
  expect(within(table).getAllByRole('columnheader').map(header => header.textContent)).toEqual(['文档名称','检测类型','检测结果','报告生成时间','操作']);
  expect(screen.getByText('错误总数：8')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '查看详情' })).toHaveAttribute('href','/thirty-rules-check/reports/pdf/example');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /删除/ })).not.toBeInTheDocument();
  expect(screen.queryByRole('menuitem', { name: /删除/ })).not.toBeInTheDocument();
});

it('reveals a single deletion only through the row menu and allows dismissing it safely', async () => {
  const { user, onDelete } = show();
  const trigger = screen.getByRole('button', { name: '更多操作：示例论文.pdf' });
  await user.click(trigger);
  expect(onDelete).not.toHaveBeenCalled();
  expect(screen.getByRole('menuitem', { name: '删除报告' })).toBeInTheDocument();
  await user.keyboard('{Escape}');
  await waitFor(() => expect(screen.queryByRole('menu')).not.toBeInTheDocument());
  expect(trigger).toHaveFocus();
  await user.click(trigger);
  await user.click(screen.getByRole('menuitem', { name: '删除报告' }));
  expect(onDelete).toHaveBeenCalledExactlyOnceWith(['example']);
});

it('reveals batch management on request and clears selection when management is closed', async () => {
  const { user, onDelete } = show();
  async function manage() {
    await user.click(screen.getByRole('button', { name: '报告管理' }));
    await user.click(screen.getByRole('menuitem', { name: '批量管理' }));
  }
  await manage();
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
  await user.click(screen.getByRole('checkbox', { name: '全选报告' }));
  expect(screen.getByRole('button', { name: '删除选中（1）' })).toBeEnabled();
  await user.click(screen.getByRole('button', { name: '完成管理' }));
  expect(screen.getByRole('button', { name: '报告管理' })).toHaveFocus();
  expect(onDelete).not.toHaveBeenCalled();
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /删除选中/ })).not.toBeInTheDocument();
  await manage();
  expect(screen.getByRole('checkbox', { name: '全选报告' })).not.toBeChecked();
  expect(screen.getByRole('button', { name: '删除选中（0）' })).toBeDisabled();
});
