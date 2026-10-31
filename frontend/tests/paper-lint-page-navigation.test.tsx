import { render, screen } from '@testing-library/react';
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

it.each([
  ['/paper-upload', '论文上传'],
  ['/abstract-check', '摘要数值语义检测'],
  ['/reports', '历史报告'],
])('renders %s without a duplicate page switching bar', async (path, title) => {
  render(<MemoryRouter initialEntries={[path]}><Routes>
    <Route path="/paper-upload" element={<NormativeCheckPage mode="thirty" />} />
    <Route path="/abstract-check" element={<NormativeCheckPage key="semantic" mode="semantic" />} />
    <Route path="/reports" element={<NormativeReportPage mode="thirty" />} />
  </Routes></MemoryRouter>);
  expect(await screen.findByRole('heading', { name: title, exact: true })).toBeInTheDocument();
  expect(screen.queryByRole('navigation', { name: '论文检测页面切换' })).not.toBeInTheDocument();
  if (path === '/reports') expect(await screen.findByText('暂无检测记录')).toBeInTheDocument();
});
