import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import NormativeCheckPage from '../src/pages/NormativeCheckPage';
import NormativeReportPage from '../src/pages/NormativeReportPage';
import { fetchPaperLintReports, fetchReviewPilotPaperLintRules } from '../src/api/paperLint';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: { id: 'navigation-student' } }),
}));
vi.mock('../src/api/paperLint', async () => ({
  ...await vi.importActual('../src/api/paperLint'),
  fetchReviewPilotPaperLintRules: vi.fn(), fetchPaperLintReports: vi.fn(),
}));
vi.mock('../src/hooks/usePaperLintRepairSuggestions', () => ({
  usePaperLintRepairSuggestions: () => ({ repairSuggestionByFindingKey: {} }),
}));
vi.mock('../src/components/paperLint/Workspace', () => ({ PaperLintWorkspace: () => null }));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  vi.mocked(fetchPaperLintReports).mockResolvedValue([]);
  vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({
    engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'existing-model', rules: [],
  });
});

it('offers the same three destinations and exactly one current page through the full switching flow', async () => {
  render(<MemoryRouter initialEntries={['/thirty-rules-check']}><Routes>
    <Route path="/thirty-rules-check" element={<NormativeCheckPage mode="thirty" />} />
    <Route path="/semantic-rules-check" element={<NormativeCheckPage key="semantic" mode="semantic" />} />
    <Route path="/thirty-rules-check/reports" element={<NormativeReportPage mode="thirty" />} />
  </Routes></MemoryRouter>);
  const destinations = [
    ['论文上传', '/thirty-rules-check'],
    ['摘要数值语义检测', '/semantic-rules-check'],
    ['历史报告', '/thirty-rules-check/reports'],
  ];
  for (const [active] of destinations) {
    const navigation = await screen.findByRole('navigation', { name: '论文检测页面切换' });
    for (const [label, path] of destinations) {
      const link = within(navigation).getByRole('link', { name: label, exact: true });
      expect(link).toHaveAttribute('href', path);
      if (label === active) expect(link).toHaveAttribute('aria-current', 'page');
      else expect(link).not.toHaveAttribute('aria-current');
    }
    expect(within(navigation).getAllByRole('link').filter(link => link.getAttribute('aria-current') === 'page')).toHaveLength(1);
    const next = destinations[destinations.findIndex(([name]) => name === active) + 1];
    if (next) fireEvent.click(within(navigation).getByRole('link', { name: next[0], exact: true }));
  }
  expect(await screen.findByText('暂无检测记录')).toBeInTheDocument();
});
