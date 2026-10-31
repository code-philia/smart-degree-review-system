import { render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import PaperLintReportPage from '../src/pages/PaperLintReportPage';
import { fetchPaperLintReport, fetchPaperLintDocumentMetrics, fetchReviewPilotPaperLintRules, type PaperLintRunResponse } from '../src/api/paperLint';

vi.mock('../src/api/paperLint', async () => ({
  ...await vi.importActual('../src/api/paperLint'),
  fetchPaperLintReport: vi.fn(), fetchPaperLintDocumentMetrics: vi.fn(), fetchReviewPilotPaperLintRules: vi.fn(),
}));
vi.mock('../src/api/feedback', async () => ({
  ...await vi.importActual('../src/api/feedback'), fetchFindingFeedback: vi.fn(async () => null), fetchSuggestionFeedback: vi.fn(async () => null),
}));
vi.mock('../src/components/paperLint/Workspace', () => ({ PaperLintWorkspace: () => null }));

const summary = { rule_count: 3, completed_rule_count: 3, unsupported_rule_count: 0, error_rule_count: 0,
  issue_rule_count: 3, finding_count: 6, error_finding_count: 1, warning_finding_count: 2, info_finding_count: 3, derived_rule_count: 0 };
const report: PaperLintRunResponse = {
  id: 'layout-report', source_filename: '实际上传文件.pdf', selected_rule_ids: ['one', 'two', 'three'], created_at: '2026-10-31T01:02:03Z',
  summary: { ...summary, ruleset_label: '当前规则' },
  result: { type: 'paper_lint', paper_title: 'PDF 内部标题', ruleset: { id: 'rules', name: '规则', version_number: 1, version_label: '当前规则' }, summary,
    rule_runs: (['error', 'warning', 'info'] as const).map((severity, index) => ({
      rule_id: ['one', 'two', 'three'][index], rule_run_id: 'run-' + index, severity, execution_status: 'completed', outcome: 'issues_found',
      findings: Array.from({ length: index + 1 }, (_, position) => ({ finding_id: `${index}-${position}`, rule_id: ['one', 'two', 'three'][index], message: '待核对问题' })),
    })),
  },
};
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchPaperLintReport).mockResolvedValue(report);
  vi.mocked(fetchPaperLintDocumentMetrics).mockResolvedValue({ page_count: 128, word_count: 12345, text_available: true, counting_method: 'cjk_characters_and_words' });
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({ engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash', rules: [] });
});
function show() {
  render(<MemoryRouter initialEntries={['/thirty-rules-check/reports/pdf/layout-report']}><Routes>
    <Route path="/thirty-rules-check/reports/pdf/:reportId" element={<PaperLintReportPage mode="thirty" />} />
  </Routes></MemoryRouter>);
}
it('puts the six real report totals beside a compact filename and completion time', async () => {
  show();
  expect(await screen.findByRole('heading', { name: '实际上传文件.pdf' })).toBeInTheDocument();
  const conclusion = screen.getByRole('region', { name: '检测结论' });
  await within(conclusion).findByText('12,345');
  for (const [label, value] of [['论文总页数', '128'], ['论文总字数', '12,345'], ['错误总数', '6'], ['严重错误数', '1'], ['警告错误数', '2'], ['提示错误数', '3']]) {
    expect((await within(conclusion).findByText(label)).closest('div')).toHaveTextContent(value);
  }
  expect(screen.getByText('规范性检测')).toBeInTheDocument();
  expect(screen.getByText('2026-10-31 09:02:03')).toHaveAttribute('dateTime', report.created_at);
  expect(screen.queryByText('各规则执行状态')).not.toBeInTheDocument();
  expect(screen.queryByText(/请优先处理严重和警告问题/)).not.toBeInTheDocument();
  expect(fetchPaperLintDocumentMetrics).toHaveBeenCalledWith('layout-report');
});
it('shows the report without waiting for PDF text statistics', async () => {
  vi.mocked(fetchPaperLintDocumentMetrics).mockImplementation(() => new Promise(() => {}));
  show();
  expect(await screen.findByRole('heading', { name: '实际上传文件.pdf' })).toBeInTheDocument();
  expect(screen.getAllByText('统计中…')).toHaveLength(2);
  expect(screen.getByRole('link', { name: '返回历史报告' })).toHaveAttribute('href', '/thirty-rules-check/reports');
});
it('does not invent zero pages or words when statistics cannot be read', async () => {
  vi.mocked(fetchPaperLintDocumentMetrics).mockRejectedValue(new Error('统计暂不可用'));
  show();
  expect(await screen.findByRole('heading', { name: '实际上传文件.pdf' })).toBeInTheDocument();
  expect(await screen.findAllByText('未统计')).toHaveLength(2);
});
it('keeps a scanned PDF page count while marking its unavailable text count', async () => {
  vi.mocked(fetchPaperLintDocumentMetrics).mockResolvedValue({ page_count: 3, word_count: null, text_available: false, counting_method: 'cjk_characters_and_words' });
  show();
  expect(await screen.findByText('未统计')).toBeInTheDocument();
  expect(screen.getByText('论文总页数').closest('div')).toHaveTextContent('3');
});

it('preserves an inconclusive semantic result without presenting an all-clear', async () => {
  const zeroSummary = { ...summary, rule_count: 1, completed_rule_count: 1, issue_rule_count: 0, finding_count: 0,
    error_finding_count: 0, warning_finding_count: 0, info_finding_count: 0 };
  vi.mocked(fetchPaperLintReport).mockResolvedValue({ ...report, result: { ...report.result, summary: zeroSummary,
    rule_runs: [{ rule_id: 'sjtu_rule_17', rule_run_id: 'semantic', severity: 'warning', execution_status: 'completed',
      outcome: 'inconclusive', message: '未能提取英文摘要，请人工核对', findings: [] }] } });
  show();
  expect(await screen.findByText('未能提取英文摘要，请人工核对')).toBeInTheDocument();
  expect(screen.getByText('部分规则无法判定')).toBeInTheDocument();
  expect(screen.queryByText('规则检查通过')).not.toBeInTheDocument();
});

it('retains confirmed-only compiler NO_ALERT wording without adding an inconclusive warning', async () => {
  const zeroSummary = { ...summary, rule_count: 1, completed_rule_count: 1, issue_rule_count: 0, finding_count: 0,
    error_finding_count: 0, warning_finding_count: 0, info_finding_count: 0 };
  vi.mocked(fetchPaperLintReport).mockResolvedValue({ ...report, result: { ...report.result, summary: zeroSummary,
    rule_runs: [{ rule_id: 'sjtu_rule_31', rule_run_id: 'compiler', severity: 'warning', execution_status: 'completed',
      outcome: 'inconclusive', publication_status: 'NO_ALERT', message: 'No confirmed violation', findings: [] }] } });
  show();
  expect(await screen.findByText('未触发告警')).toBeInTheDocument();
  expect(screen.queryByText('部分规则无法判定')).not.toBeInTheDocument();
});
