import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import NormativeReportPage from '../src/pages/NormativeReportPage';
import { fetchPaperLintReports } from '../src/api/paperLint';

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: { id: 'student01' } }),
}));
vi.mock('../src/api/paperLint', async () => {
  const actual = await vi.importActual<typeof import('../src/api/paperLint')>('../src/api/paperLint');
  return { ...actual, fetchPaperLintReports: vi.fn() };
});
vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return { ...actual, fetchNormativeDetectionHistory: vi.fn(async () => []) };
});

describe('saved PDF report history', () => {
  it('labels an unsupported-only result as inconclusive', async () => {
    vi.mocked(fetchPaperLintReports).mockResolvedValue([{
      id: 'unsupported-24', source_filename: '待检论文.pdf',
      selected_rule_ids: ['sjtu_rule_24'], created_at: '2026-09-26T04:30:00.000Z',
      summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0,
        info_finding_count: 0, rule_count: 1, unsupported_rule_count: 1,
        error_rule_count: 0, ruleset_label: '本地四规则' },
    }]);
    render(<MemoryRouter initialEntries={['/normative-reports']}>
      <Routes><Route path="/normative-reports" element={<NormativeReportPage />} /></Routes>
    </MemoryRouter>);
    expect(await screen.findByText('待检论文.pdf')).toBeInTheDocument();
    expect(screen.getByText('部分规则无法判定')).toBeInTheDocument();
    expect(screen.queryByText('未发现问题')).not.toBeInTheDocument();
  });
});