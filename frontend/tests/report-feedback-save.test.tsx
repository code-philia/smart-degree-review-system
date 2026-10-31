import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import PaperLintReportPage from '../src/pages/PaperLintReportPage';
import NormativeCheckPage from '../src/pages/NormativeCheckPage';
import { saveFindingFeedback, saveSuggestionFeedback } from '../src/api/feedback';
import { fixture } from './fixtures/reportExport';
import { flattenPaperLintFindings } from '../src/components/paperLint/model';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: { id: 'test' } }),
}));
const repairState = vi.hoisted(() => ({ repairSuggestionByFindingKey: {}, loadRepairSuggestion: () => {} }));
vi.mock('../src/hooks/usePaperLintRepairSuggestions', () => ({ usePaperLintRepairSuggestions: () => repairState }));

vi.mock('../src/components/paperLint/PdfPane', () => ({ PdfPane: () => null }));
vi.mock('../src/api/paperLint', async () => ({
  ...(await vi.importActual('../src/api/paperLint')),
  fetchPaperLintReport: vi.fn(async () => ({ ...fixture, id: 'r' })),
  fetchPaperLintJob: vi.fn(async () => ({ status: 'completed', report_id: 'r' })),
  fetchPaperLintDocumentMetrics: vi.fn(async () => ({ page_count: 20, word_count: 12345, text_available: true })),
  fetchReviewPilotPaperLintRules: vi.fn(async () => ({
    rules: [
      { rule_id: 'first', title: '第一项', enabled_in_mvp: true },
      { rule_id: 'second', title: '第二项', enabled_in_mvp: true },
      { rule_id: 'sjtu_rule_15', title: '公式引用', enabled_in_mvp: false },
    ],
  })),
}));
vi.mock('../src/api/feedback', async () => ({
  ...(await vi.importActual('../src/api/feedback')),
  fetchFindingFeedback: vi.fn(async () => ({
    id: 'feedback',
    feedback_value: 'negative',
    reason_code: null,
    reason_text: null,
  })),
  fetchSuggestionFeedback: vi.fn(async () => ({ id: 'suggestion-feedback', feedback_value: 'negative' })),
  saveFindingFeedback: vi.fn(),
  saveSuggestionFeedback: vi.fn(),
}));

it.each([
  ['history', 'finding'],
  ['live', 'finding'],
  ['history', 'suggestion'],
  ['live', 'suggestion'],
] as const)('does not convert a rejected %s %s feedback save into success, and permits retry', async (page, target) => {
  repairState.repairSuggestionByFindingKey =
    target === 'suggestion'
      ? {
          [flattenPaperLintFindings(fixture.result)[0].key]: {
            suggestion_id: 'suggestion',
            actions: [],
            status: 'suggested',
          },
        }
      : {};
  localStorage.setItem(
    'paper-lint-active-job:test',
    JSON.stringify({ jobId: 'job', requestId: 'request', filename: 'test.pdf', selectedRuleIds: [] }),
  );
  const user = userEvent.setup();
  const save = target === 'finding' ? saveFindingFeedback : saveSuggestionFeedback;
  vi.mocked(save).mockRejectedValueOnce(new Error('保存服务暂不可用'));
  render(
    <MemoryRouter initialEntries={['/reports/r']}>
      <Routes>
        <Route
          path="/reports/:reportId"
          element={page === 'history' ? <PaperLintReportPage /> : <NormativeCheckPage />}
        />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByRole('heading', { name: '规则 3：公式引用' })).toBeInTheDocument();
  const controls = within(
    (await screen.findByText(target === 'finding' ? '这个问题的判断是否准确？' : '这条修复建议是否有帮助？')).closest(
      '[aria-busy]',
    )! as HTMLElement,
  );
  const submit = await controls.findByRole('button', { name: '提交反馈' });
  await user.click(submit);
  expect(await screen.findByRole('alert')).toHaveTextContent('保存服务暂不可用');
  expect(screen.queryByRole('heading', { name: '提交成功' })).not.toBeInTheDocument();
  vi.mocked(save).mockResolvedValueOnce({
    id: 'feedback',
    feedback_value: 'negative',
    reason_code: target === 'finding' ? 'false_positive' : 'incorrect',
    reason_text: '已核对',
  } as never);
  const reason = target === 'finding' ? 'false_positive' : 'incorrect';
  await user.selectOptions(controls.getByRole('combobox', { name: '负面反馈原因' }), reason);
  await user.type(controls.getByRole('textbox', { name: '反馈补充说明' }), '已核对');
  await user.click(submit);
  expect(await screen.findByRole('heading', { name: '提交成功' })).toBeInTheDocument();
  await waitFor(() =>
    expect(save).toHaveBeenLastCalledWith(
      'r',
      ...(target === 'finding'
        ? [fixture.result.rule_runs[0].rule_id, fixture.result.rule_runs[0].findings[0].finding_id]
        : ['suggestion']),
      { feedback_value: 'negative', reason_code: reason, reason_text: '已核对' },
    ),
  );
});
