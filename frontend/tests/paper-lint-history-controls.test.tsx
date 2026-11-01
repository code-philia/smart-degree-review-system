import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import NormativeReportPage from '../src/pages/NormativeReportPage';
import { deletePaperLintReport, deletePaperLintReports, fetchPaperLintReports } from '../src/api/paperLint';
const { user } = vi.hoisted(() => ({ user: { id: 'student01' } }));
vi.mock('../src/auth/AuthSessionProvider', () => ({ useAuthSession: () => ({ status: 'authenticated', user }) }));
vi.mock('../src/api/paperLint', async () => ({ ...await vi.importActual('../src/api/paperLint'),
  deletePaperLintReport: vi.fn(), deletePaperLintReports: vi.fn(), fetchPaperLintReports: vi.fn(),
}));
const rows = ['first', 'second'].map(id => ({ id, source_filename: `${id}.pdf`, selected_rule_ids: ['sjtu_rule_22'], created_at: '2026-10-29T08:00:00Z',
  summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0, info_finding_count: 0, rule_count: 1, unsupported_rule_count: 0, error_rule_count: 0, ruleset_label: '' } }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchPaperLintReports).mockResolvedValue(rows);
  vi.mocked(deletePaperLintReport).mockResolvedValue(undefined);
  vi.mocked(deletePaperLintReports).mockResolvedValue(['first', 'second']);
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});
afterEach(() => vi.restoreAllMocks());
const show = async () => { render(<MemoryRouter><NormativeReportPage mode="thirty" /></MemoryRouter>); await screen.findByText('first.pdf'); };
async function deleteFirst() {
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: '更多操作：first.pdf' }));
  await user.click(screen.getByRole('menuitem', { name: '删除报告' }));
}

it('confirms a single deletion and removes just that report from history', async () => {
  await show();
  await deleteFirst();
  await waitFor(() => expect(screen.queryByText('first.pdf')).not.toBeInTheDocument());
  expect(window.confirm).toHaveBeenCalled();
  expect(deletePaperLintReport).toHaveBeenCalledWith('first');
  expect(screen.getByText('second.pdf')).toBeInTheDocument();
});

it('deletes the selected reports as one confirmed batch', async () => {
  await show();
  const user = userEvent.setup();
  await user.click(screen.getByRole('button', { name: '报告管理' }));
  await user.click(screen.getByRole('menuitem', { name: '批量管理' }));
  fireEvent.click(screen.getByRole('checkbox', { name: '全选报告' }));
  fireEvent.click(screen.getByRole('button', { name: '删除选中（2）' }));
  expect(await screen.findByText('暂无检测记录')).toBeInTheDocument();
  expect(deletePaperLintReports).toHaveBeenCalledWith(['first', 'second']);
  expect(window.confirm).toHaveBeenCalledTimes(1);
});

it('keeps reports when confirmation is declined or deletion fails', async () => {
  await show();
  vi.mocked(window.confirm).mockReturnValueOnce(false);
  await deleteFirst();
  expect(deletePaperLintReport).not.toHaveBeenCalled();
  vi.mocked(deletePaperLintReport).mockRejectedValueOnce(new Error('删除未完成'));
  await deleteFirst();
  expect(await screen.findByText('删除未完成')).toBeInTheDocument();
  expect(screen.getByText('first.pdf')).toBeInTheDocument();
  expect(screen.getByText('second.pdf')).toBeInTheDocument();
});


it('shows newly saved reports containing all fifteen enabled rules, including external references', async () => {
  const selected_rule_ids = [
    'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28', 'sjtu_rule_31', 'sjtu_rule_32',
    'required_section_completeness_check', 'chinese_english_symbol_mix_check', 'keyword_count_check',
    'abstract_object_number_check', 'chapter_new_page_check', 'typo_detection_check',
    'bilingual_keywords_correspondence_check', 'bilingual_abstract_consistency_check',
    'abstract_numeric_consistency_check',
  ];
  vi.mocked(fetchPaperLintReports).mockResolvedValue([
    { ...rows[0], id: 'new-report', source_filename: 'newly-finished.pdf', selected_rule_ids },
    { ...rows[1], id: 'external-only', source_filename: 'external-references.pdf', selected_rule_ids: ['sjtu_rule_32'] },
    { ...rows[0], id: 'basic-only', source_filename: 'basic-only.pdf', selected_rule_ids: ['toc_format_check'] },
  ]);
  render(<MemoryRouter><NormativeReportPage mode="thirty" /></MemoryRouter>);
  expect(await screen.findByText('newly-finished.pdf')).toBeInTheDocument();
  expect(screen.getByText('external-references.pdf')).toBeInTheDocument();
  expect(screen.queryByText('basic-only.pdf')).not.toBeInTheDocument();
  expect(screen.getAllByRole('link', { name: '查看详情' }).map(link => link.getAttribute('href')))
    .toContain('/reports/pdf/new-report');
});
