import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import {
  fetchPaperLintDocumentMetrics, fetchPaperLintReport, fetchReviewPilotPaperLintRules,
  type PaperLintRule, type PaperLintRunResponse,
} from '../src/api/paperLint';
import PaperLintReportPage from '../src/pages/PaperLintReportPage';
import { fixture } from './fixtures/reportExport';

vi.mock('../src/api/paperLint', async () => ({
  ...await vi.importActual('../src/api/paperLint'),
  fetchPaperLintReport: vi.fn(), fetchPaperLintDocumentMetrics: vi.fn(), fetchReviewPilotPaperLintRules: vi.fn(),
}));
vi.mock('../src/api/feedback', async () => ({
  ...await vi.importActual('../src/api/feedback'),
  fetchFindingFeedback: vi.fn(async () => null), fetchSuggestionFeedback: vi.fn(async () => null),
}));
vi.mock('../src/components/paperLint/Workspace', () => ({ PaperLintWorkspace: () => null }));

const catalog: PaperLintRule[] = [
  { rule_id: 'sjtu_rule_15', title: '图表编号', description: '核对图表编号与正文引用是否对应。',
    default_severity: 'warning', default_enabled: true, execution_mode: 'deterministic', uses_external_model: false, available: true },
  { rule_id: 'unselected', title: '未选择的规则', description: '不属于本次检测。',
    default_severity: 'warning', default_enabled: true, execution_mode: 'deterministic', uses_external_model: false, available: true },
];
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchPaperLintReport).mockResolvedValue({ ...fixture, selected_rule_ids: ['sjtu_rule_15', 'archived-rule', 'sjtu_rule_15'] });
  vi.mocked(fetchPaperLintDocumentMetrics).mockResolvedValue({ page_count: 20, word_count: 12345, text_available: true, counting_method: 'cjk_characters_and_words' });
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({ engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash', rules: catalog });
});
function show() {
  render(<MemoryRouter initialEntries={['/reports/export-report']}><Routes>
    <Route path="/reports/:reportId" element={<PaperLintReportPage mode="thirty" />} />
  </Routes></MemoryRouter>);
}

it('shows saved selected scope as a collapsed count and unfolds catalog titles and descriptions', async () => {
  show();
  const title = await screen.findByText('本次检测范围');
  const details = title.closest('details')!;
  expect(details).not.toHaveAttribute('open');
  expect(within(details).getByText('已选择 2 项规则')).toBeVisible();
  await userEvent.click(title.closest('summary')!);
  expect(details).toHaveAttribute('open');
  expect(await within(details).findByText('图表编号')).toBeVisible();
  expect(within(details).getByText('核对图表编号与正文引用是否对应。')).toBeVisible();
  expect(within(details).getByText('archived-rule')).toBeVisible();
  expect(within(details).getByText('规则说明暂不可用（目录中未提供）。')).toBeVisible();
  expect(within(details).queryByText('未选择的规则')).not.toBeInTheDocument();
  expect(within(details).queryByText(/通过|执行失败|无法判定/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: '下载检测报告' })).toBeInTheDocument();
  expect(fetchReviewPilotPaperLintRules).toHaveBeenCalledTimes(1);
});

it('keeps scope visible using recorded IDs when the existing catalog read fails', async () => {
  vi.mocked(fetchReviewPilotPaperLintRules).mockRejectedValue(new Error('目录暂不可用'));
  show();
  const title = await screen.findByText('本次检测范围');
  await userEvent.click(title.closest('summary')!);
  const details = title.closest('details')!;
  expect(within(details).getByText('sjtu_rule_15')).toBeVisible();
  expect(within(details).getAllByText('规则说明暂不可用（目录中未提供）。')).toHaveLength(2);
});

it.each([{ name: 'empty', ids: [] }, { name: 'absent', ids: undefined }])(
  'opens a legacy report with $name selections and shows its executed scope',
  async ({ ids }) => {
    vi.mocked(fetchPaperLintReport).mockResolvedValue({ ...fixture, selected_rule_ids: ids } as PaperLintRunResponse);
    show();
    const title = await screen.findByText('本次检测范围');
    const details = title.closest('details')!;
    expect(within(details).getByText('已选择 1 项规则')).toBeVisible();
    await userEvent.click(title.closest('summary')!);
    expect(await within(details).findByText('图表编号')).toBeVisible();
  },
);
