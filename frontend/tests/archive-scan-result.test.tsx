import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import ArchiveScanResultPage from '../src/pages/ArchiveScanResultPage';
import { fetchArchiveCatalog, fetchArchiveDocument } from '../src/api/archiveScans';
import { fetchCurrentSession } from '../src/api/authSession';
vi.mock('../src/api/authSession', async () => ({
  ...(await vi.importActual('../src/api/authSession')),
  fetchCurrentSession: vi.fn(),
}));
vi.mock('../src/api/archiveScans', () => ({
  fetchArchiveCatalog: vi.fn(),
  fetchArchiveDocument: vi.fn(),
  archivePdfUrl: (job: string, doc: string) => `/api/normative/archive-scans/jobs/${job}/documents/${doc}/pdf`,
}));
vi.mock('../src/components/paperLint/Workspace', () => ({
  PaperLintWorkspace: ({
    file,
    findings,
  }: {
    file: { url: string };
    findings: Array<{ finding: { message: string } }>;
  }) => (
    <div data-testid="workspace">
      {file.url} {findings.map((item) => item.finding.message).join(' ')}
    </div>
  ),
}));
const admin = {
  id: 'admin',
  username: 'admin',
  role: 'COLLEGE_ADMIN',
  collegeId: 'college01',
  supervisorId: null,
  scope: 'COLLEGE',
};
beforeEach(() => {
  vi.mocked(fetchCurrentSession).mockResolvedValue({ user: admin as never });
  vi.mocked(fetchArchiveCatalog).mockResolvedValue({
    rules: [{ rule_id: 'sjtu_rule_18', title: '规则 18', description: '' }] as never,
    paper_count: 479,
  });
  vi.mocked(fetchArchiveDocument).mockResolvedValue({
    document: {
      id: 'doc',
      job_id: 'job',
      filename: '论文.pdf',
      relative_path: '硕士/论文.pdf',
      status: 'completed',
      finding_count: 1,
      rule_outcomes: { sjtu_rule_18: 'issues_found' },
      result: {
        type: 'paper_lint',
        paper_title: '论文',
        ruleset: { id: 'x', name: 'x', version_number: 1, version_label: 'x' },
        summary: { finding_count: 1 },
        rule_runs: [
          {
            rule_run_id: 'x',
            rule_id: 'sjtu_rule_18',
            severity: 'warning',
            execution_status: 'completed',
            outcome: 'issues_found',
            findings: [
              {
                finding_id: 'f1',
                rule_id: 'sjtu_rule_18',
                message: '公式引用未找到目标',
                location: {
                  type: 'pdf_bbox',
                  page_number: 3,
                  bounding_rect: { x1: 1, y1: 1, x2: 2, y2: 2, width: 100, height: 100, page_number: 3 },
                  rects: [],
                },
              },
            ],
          },
        ],
      },
    } as never,
  });
});
describe('archive paper result', () => {
  it('shows the issue and streams the archived PDF URL to the location viewer', async () => {
    render(
      <MemoryRouter initialEntries={['/thirty-rules-check/archive/jobs/job/documents/doc']}>
        <Routes>
          <Route
            path="/thirty-rules-check/archive/jobs/:jobId/documents/:documentId"
            element={
              <AuthSessionProvider>
                <ArchiveScanResultPage />
              </AuthSessionProvider>
            }
          />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText('论文.pdf')).toBeInTheDocument();
    expect(screen.getByTestId('workspace')).toHaveTextContent(
      '/api/normative/archive-scans/jobs/job/documents/doc/pdf',
    );
    expect(screen.getByTestId('workspace')).toHaveTextContent('公式引用未找到目标');
  });
});
