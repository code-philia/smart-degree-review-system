import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import NormativeReportPage from '../src/pages/NormativeReportPage';
import { deletePaperLintReport, deletePaperLintReports, fetchPaperLintReports } from '../src/api/paperLint';
import { setLocale } from '../src/i18n/locale';
const { user } = vi.hoisted(() => ({ user: { id: 'student01' } }));
vi.mock('../src/auth/AuthSessionProvider', () => ({ useAuthSession: () => ({ status: 'authenticated', user }) }));
vi.mock('../src/api/paperLint', async () => ({ ...await vi.importActual('../src/api/paperLint'),
  deletePaperLintReport: vi.fn(), deletePaperLintReports: vi.fn(), fetchPaperLintReports: vi.fn(),
}));
const rows = ['first', 'second'].map(id => ({ id, source_filename: `${id}.pdf`, selected_rule_ids: ['sjtu_rule_22'], created_at: '2026-10-29T08:00:00Z',
  summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0, info_finding_count: 0, rule_count: 1, unsupported_rule_count: 0, error_rule_count: 0, ruleset_label: '' } }));
beforeEach(() => {
  vi.clearAllMocks(); setLocale('zh');
  vi.mocked(fetchPaperLintReports).mockResolvedValue(rows);
  vi.mocked(deletePaperLintReport).mockResolvedValue(undefined);
  vi.mocked(deletePaperLintReports).mockResolvedValue(['first', 'second']);
  vi.spyOn(window, 'confirm').mockReturnValue(false);
});
afterEach(() => {vi.restoreAllMocks(); act(()=>setLocale('zh'));});
const show = async () => { render(<MemoryRouter><NormativeReportPage mode="thirty" /></MemoryRouter>); await screen.findByText('first.pdf'); };
async function deleteFirst() {
  const row = screen.getByRole('link', { name: 'first.pdf' }).closest('tr')!;
  const trigger=within(row).getByRole('button', { name: '删除报告', exact: true });
  await userEvent.setup().click(trigger);
  return trigger;
}
const dialog=()=>screen.getByRole('alertdialog');
const confirmDelete=()=>userEvent.setup().click(within(dialog()).getByRole('button',{name:'确认删除',exact:true}));

it('opens an in-app confirmation before a single deletion and removes only the confirmed report', async () => {
  await show();
  expect(screen.queryByText('论文规范性检测', { exact: true })).not.toBeInTheDocument();
  await deleteFirst();
  expect(dialog()).toHaveAccessibleName('删除报告？');
  expect(within(dialog()).getByText('first.pdf')).toBeInTheDocument();
  expect(deletePaperLintReport).not.toHaveBeenCalled();
  expect(window.confirm).not.toHaveBeenCalled();
  await confirmDelete();
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(screen.queryByText('first.pdf')).not.toBeInTheDocument();
  expect(deletePaperLintReport).toHaveBeenCalledExactlyOnceWith('first');
  expect(screen.getByText('second.pdf')).toBeInTheDocument();
});

it('cancels by button or Escape without deleting and restores focus to the original row action', async () => {
  await show(); const user=userEvent.setup();
  const trigger=await deleteFirst();
  await user.click(within(dialog()).getByRole('button',{name:'取消',exact:true}));
  await waitFor(()=>expect(trigger).toHaveFocus());
  expect(deletePaperLintReport).not.toHaveBeenCalled();
  await user.click(trigger); await user.keyboard('{Escape}');
  await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(trigger).toHaveFocus(); expect(deletePaperLintReport).not.toHaveBeenCalled();
});

it('confirms a batch in the same in-app dialog while preserving selection on cancel', async () => {
  await show(); const user=userEvent.setup();
  await user.click(screen.getByRole('button', { name: '批量管理', exact: true }));
  fireEvent.click(screen.getByRole('checkbox', { name: '全选报告' }));
  await user.click(screen.getByRole('button', { name: '删除选中（2）' }));
  expect(dialog()).toHaveAccessibleName('删除选中的报告？');
  await user.click(within(dialog()).getByRole('button',{name:'取消',exact:true}));
  expect(screen.getByRole('checkbox',{name:'全选报告'})).toBeChecked();
  expect(deletePaperLintReports).not.toHaveBeenCalled();
  await user.click(screen.getByRole('button',{name:'删除选中（2）'}));
  await confirmDelete();
  expect(await screen.findByText('暂无检测记录')).toBeInTheDocument();
  expect(deletePaperLintReports).toHaveBeenCalledExactlyOnceWith(['first','second']);
  expect(window.confirm).not.toHaveBeenCalled();
});

it('keeps the dialog and records after failure and retries the same deletion', async () => {
  await show(); vi.mocked(deletePaperLintReport).mockRejectedValueOnce(new Error('删除未完成'));
  await deleteFirst(); await confirmDelete();
  expect(await within(dialog()).findByRole('alert')).toHaveTextContent('删除未完成');
  expect(within(dialog()).getByText('first.pdf')).toBeInTheDocument();
  await confirmDelete();
  await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
  expect(deletePaperLintReport).toHaveBeenCalledTimes(2);
  expect(screen.getByText('second.pdf')).toBeInTheDocument();
});

it('blocks duplicate confirmation and Escape while the deletion is pending', async () => {
  await show(); let finish!:()=>void;
  vi.mocked(deletePaperLintReport).mockReturnValueOnce(new Promise(resolve=>{finish=()=>resolve(undefined)}));
  await deleteFirst(); const confirm=within(dialog()).getByRole('button',{name:'确认删除',exact:true});
  fireEvent.click(confirm); fireEvent.click(confirm);
  expect(deletePaperLintReport).toHaveBeenCalledTimes(1);
  expect(within(dialog()).getByRole('button',{name:'正在删除…'})).toBeDisabled();
  expect(within(dialog()).getByRole('button',{name:'取消',exact:true})).toBeDisabled();
  await userEvent.setup().keyboard('{Escape}'); expect(dialog()).toBeInTheDocument();
  await act(async()=>finish());
  await waitFor(()=>expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
});

it('keeps original filenames intact in the English confirmation', async () => {
  const filename='检测规则_'+('long-filename_'.repeat(8))+'.pdf';
  vi.mocked(fetchPaperLintReports).mockResolvedValue([{...rows[0],source_filename:filename}]);
  act(()=>setLocale('en'));
  render(<MemoryRouter><NormativeReportPage mode="thirty" /></MemoryRouter>);
  await screen.findByRole('link',{name:filename});
  await userEvent.setup().click(screen.getByRole('button',{name:'Delete report',exact:true}));
  expect(dialog()).toHaveAccessibleName('Delete report?');
  expect(within(dialog()).getByText(filename)).toBeInTheDocument();
  expect(within(dialog()).getByRole('button',{name:'Cancel',exact:true})).toBeInTheDocument();
  expect(within(dialog()).getByText('The report and its PDF will be permanently deleted. This cannot be undone.')).toBeInTheDocument();
});

it('shows newly saved reports containing all fifteen enabled rules, including external references', async () => {
  const selected_rule_ids = ['sjtu_rule_18','sjtu_rule_22','sjtu_rule_24','sjtu_rule_28','sjtu_rule_31','sjtu_rule_32','required_section_completeness_check','chinese_english_symbol_mix_check','keyword_count_check','abstract_object_number_check','chapter_new_page_check','typo_detection_check','bilingual_keywords_correspondence_check','bilingual_abstract_consistency_check','abstract_numeric_consistency_check'];
  vi.mocked(fetchPaperLintReports).mockResolvedValue([
    {...rows[0],id:'new-report',source_filename:'newly-finished.pdf',selected_rule_ids},
    {...rows[1],id:'external-only',source_filename:'external-references.pdf',selected_rule_ids:['sjtu_rule_32']},
    {...rows[0],id:'basic-only',source_filename:'basic-only.pdf',selected_rule_ids:['toc_format_check']},
  ]);
  render(<MemoryRouter><NormativeReportPage mode="thirty" /></MemoryRouter>);
  expect(await screen.findByText('newly-finished.pdf')).toBeInTheDocument();
  expect(screen.getByText('external-references.pdf')).toBeInTheDocument();
  expect(screen.queryByText('basic-only.pdf')).not.toBeInTheDocument();
  expect(screen.getAllByRole('link',{name:'查看详情'}).map(link=>link.getAttribute('href'))).toContain('/reports/pdf/new-report');
});

it('uses plural English wording for a multi-report deletion', async()=>{
  await show(); act(()=>setLocale('en')); const user=userEvent.setup();
  await user.click(screen.getByRole('button',{name:'Manage records',exact:true}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Select all reports',exact:true}));
  await user.click(screen.getByRole('button',{name:/Delete selected/}));
  expect(dialog()).toHaveAccessibleName('Delete selected reports?');
  expect(within(dialog()).getByText('The selected reports and their PDFs will be permanently deleted. This cannot be undone.')).toBeInTheDocument();
});

it('returns focus to the remaining history view after the last report is removed',async()=>{
  vi.mocked(fetchPaperLintReports).mockResolvedValue([rows[0]]);
  await show(); await deleteFirst(); await confirmDelete();
  await screen.findByText('暂无检测记录');
  await waitFor(()=>{
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement).toContainElement(screen.getByRole('heading',{name:'历史报告',exact:true}));
  });
});
