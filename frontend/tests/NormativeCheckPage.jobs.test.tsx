import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession } from '../src/api/authSession';
import { fetchReviewPilotPaperLintRules, runReviewPilotPaperLint,
  fetchPaperLintJob, fetchPaperLintReport } from '../src/api/paperLint';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return { ...actual, fetchCurrentSession: vi.fn() };
});
vi.mock('../src/api/paperLint', async () => {
  const actual = await vi.importActual<typeof import('../src/api/paperLint')>('../src/api/paperLint');
  return { ...actual, fetchReviewPilotPaperLintRules: vi.fn(),
    runReviewPilotPaperLint: vi.fn(), fetchPaperLintJob: vi.fn(), fetchPaperLintReport: vi.fn() };
});
vi.mock('../src/components/paperLint/Workspace', () => ({
  PaperLintWorkspace: () => <div data-testid="paper-lint-workspace" />,
}));

const rule = { rule_id: 'sjtu_rule_13', title: '规则 13 · 图缺少图题',
  description: '图题', default_severity: 'warning' as const, default_enabled: false,
  execution_mode: 'deterministic' as const, uses_external_model: false,
  available: true, source: 'sjtu-six-pdf' as const };
const report = {
  id: 'job-1', source_filename: 'test.pdf', created_at: '2026-09-27T00:00:00.000Z',
  selected_rule_ids: ['sjtu_rule_13'],
  summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0,
    info_finding_count: 0, rule_count: 1, unsupported_rule_count: 0, error_rule_count: 0, ruleset_label: '六规则' },
  result: { type: 'paper_lint' as const, paper_title: 'test',
    ruleset: { id: 'six', name: 'six', version_number: 1, version_label: 'six' },
    rule_runs: [], summary: { rule_count: 1, completed_rule_count: 1,
      unsupported_rule_count: 0, error_rule_count: 0, issue_rule_count: 0,
      finding_count: 0, error_finding_count: 0, warning_finding_count: 0,
      info_finding_count: 0, derived_rule_count: 0 } },
};

describe('MinerU background PDF review', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: {
      id: 'student01', username: 'student01', role: 'STUDENT',
      collegeId: 'college01', supervisorId: 'supervisor01', scope: 'COLLEGE',
    } });
    vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({
      engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash', rules: [rule],
    });
    vi.mocked(runReviewPilotPaperLint).mockReset();
    vi.mocked(fetchPaperLintJob).mockReset();
    vi.mocked(fetchPaperLintReport).mockReset();
  });

  it('starts without a MinerU consent checkbox, polls 202 job and opens saved report', async () => {
    vi.mocked(runReviewPilotPaperLint).mockResolvedValue({
      job_id: 'job-1', status: 'pending', report_id: null, error_message: null,
      created_at: '', updated_at: '',
    });
    vi.mocked(fetchPaperLintJob).mockResolvedValue({
      job_id: 'job-1', status: 'completed', report_id: 'job-1', error_message: null,
      created_at: '', updated_at: '',
    });
    vi.mocked(fetchPaperLintReport).mockResolvedValue(report);
    const user = userEvent.setup();
    render(<MemoryRouter initialEntries={['/thirty-rules-check']}>
      <AuthSessionProvider><App /></AuthSessionProvider>
    </MemoryRouter>);
    await user.upload(await screen.findByLabelText('上传待审查 PDF'),
      new File(['%PDF-1.7\n'], 'test.pdf', { type: 'application/pdf' }));
    await user.click(screen.getByRole('checkbox', { name: /规则 13/ }));
    expect(screen.queryByText(/我确认.*MinerU/)).toBeNull();
    await user.click(screen.getByRole('button', { name: '开始检查' }));
    await waitFor(() => expect(fetchPaperLintJob).toHaveBeenCalledWith('job-1'), { timeout: 4000 });
    expect(await screen.findByText('未发现问题')).toBeTruthy();
    expect(fetchPaperLintReport).toHaveBeenCalledWith('job-1');
  });
});
