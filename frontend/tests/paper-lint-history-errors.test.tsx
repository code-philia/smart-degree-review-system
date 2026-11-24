import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import NormativeReportPage from '../src/pages/NormativeReportPage';
import { fetchPaperLintReports } from '../src/api/paperLint';

const session = vi.hoisted(() => ({ user: { id: 'student01' } }));
vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({ status: 'authenticated', user: session.user }),
}));
vi.mock('../src/api/paperLint', async () => ({
  ...await vi.importActual<typeof import('../src/api/paperLint')>('../src/api/paperLint'),
  fetchPaperLintReports: vi.fn(),
}));

beforeEach(() => { vi.mocked(fetchPaperLintReports).mockReset(); session.user.id = 'student01'; });
const show = () => render(<MemoryRouter initialEntries={['/reports']}><NormativeReportPage mode="thirty" /></MemoryRouter>);

describe('PDF history request outcomes', () => {
  for (const status of [403, 500]) it(`shows an error instead of an empty history after HTTP ${status}`, async () => {
    vi.mocked(fetchPaperLintReports).mockRejectedValue(new Error(`Request failed with status code ${status}`));
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent(`Request failed with status code ${status}`);
    expect(screen.queryByText('暂无检测记录')).not.toBeInTheDocument();
    expect(screen.queryByRole('table', { name: '规范性检测报告' })).not.toBeInTheDocument();
  });

  it('retains the genuine successful empty state', async () => {
    vi.mocked(fetchPaperLintReports).mockResolvedValue([]);
    show();
    expect(await screen.findByText('暂无检测记录')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });

  it('does not retain previous account rows when the next account history request fails', async () => {
    vi.mocked(fetchPaperLintReports).mockResolvedValueOnce([{
      id: 'previous-account-report', source_filename: 'previous-account.pdf', selected_rule_ids: ['keyword_count_check'],
      created_at: '2026-11-25T00:00:00Z',
      summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0, info_finding_count: 0,
        rule_count: 1, unsupported_rule_count: 0, error_rule_count: 0, ruleset_label: '本地规则' },
    }]);
    const view = show();
    expect(await screen.findByText('previous-account.pdf')).toBeInTheDocument();
    session.user.id = 'student02';
    vi.mocked(fetchPaperLintReports).mockRejectedValueOnce(new Error('检测报告加载失败'));
    view.rerender(<MemoryRouter initialEntries={['/reports']}><NormativeReportPage mode="thirty" /></MemoryRouter>);
    expect(await screen.findByRole('alert')).toHaveTextContent('检测报告加载失败');
    expect(screen.queryByText('previous-account.pdf')).not.toBeInTheDocument();
    expect(screen.queryByRole('table', { name: '规范性检测报告' })).not.toBeInTheDocument();
  });
});
