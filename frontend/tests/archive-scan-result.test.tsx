import userEvent from '@testing-library/user-event';
import { fetchArchiveFindingRepairSuggestions } from '../src/api/repairSuggestions';
import { render, screen, waitFor } from '@testing-library/react';
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
vi.mock('../src/api/repairSuggestions', async () => ({...(await vi.importActual('../src/api/repairSuggestions')), fetchArchiveFindingRepairSuggestions:vi.fn().mockResolvedValue([])}));
vi.mock('../src/components/paperLint/Workspace', () => ({
  PaperLintWorkspace: ({
    file,
    findings,
    openPdfUrl,
    onLoadRepairSuggestion,
  }: {
    file: { url: string };
    findings: Array<{ finding: { message: string } }>;
    openPdfUrl?: string;
    onLoadRepairSuggestion?: (item: any) => void;
  }) => (
    <div data-testid="workspace" data-open-pdf-url={openPdfUrl}>
      {file.url} {findings.map((item) => item.finding.message).join(' ')}
      <button onClick={() => onLoadRepairSuggestion?.(findings[0])}>读取保存建议</button>
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
    expect(screen.getByTestId('workspace')).toHaveAttribute(
      'data-open-pdf-url',
      '/api/normative/archive-scans/jobs/job/documents/doc/pdf',
    );
    expect(screen.queryByRole('link', { name: '在浏览器中打开完整 PDF' })).not.toBeInTheDocument();
  });
});

it('shows a reviewed false-positive removal while keeping rule 22 in the report', async () => {
  const { document } = await fetchArchiveDocument('job', 'doc');
  const run = document.result!.rule_runs[0];
  vi.mocked(fetchArchiveCatalog).mockResolvedValue({
    rules: [{ rule_id: 'sjtu_rule_22', title: '规则 22', description: '' }] as never,
    paper_count: 479,
  });
  vi.mocked(fetchArchiveDocument).mockResolvedValue({ document: {
    ...document,
    finding_count: 0,
    rule_outcomes: { sjtu_rule_22: 'passed' },
    result: {
      ...document.result,
      summary: { ...document.result!.summary, finding_count: 0, issue_rule_count: 0 },
      rule_runs: [{ ...run, rule_id: 'sjtu_rule_22', outcome: 'passed', findings: [] }],
      finding_reviews: [{
        rule_id: 'sjtu_rule_22', finding_id: 'f1', disposition: 'false_positive',
        reviewed_at: '2026-10-20T12:00:00Z', reason: '用户确认误报',
        original_finding: run.findings[0],
      }],
    },
  } as never });
  render(
    <MemoryRouter initialEntries={['/thirty-rules-check/archive/jobs/job/documents/doc']}>
      <Routes><Route path="/thirty-rules-check/archive/jobs/:jobId/documents/:documentId"
        element={<AuthSessionProvider><ArchiveScanResultPage /></AuthSessionProvider>} /></Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText('已移除 1 条经确认的误报')).toBeInTheDocument();
  expect(screen.getByText('规则 22')).toBeInTheDocument();
  expect(screen.getByText('通过 · 0 处')).toBeInTheDocument();
  expect(screen.getByText('未发现问题')).toBeInTheDocument();
  expect(screen.getByTestId('workspace')).not.toHaveTextContent('公式引用未找到目标');
});

it('reads a merged finding suggestion using its original scan identity',async()=>{
 const {document}=await fetchArchiveDocument('job','doc');
 vi.mocked(fetchArchiveDocument).mockResolvedValue({document:{...document,repair_sources:{sjtu_rule_18:{job_id:'original-job',document_id:'original-doc'}}}});
 render(<MemoryRouter initialEntries={['/thirty-rules-check/archive/jobs/archive-479-combined/documents/doc']}><Routes><Route path="/thirty-rules-check/archive/jobs/:jobId/documents/:documentId" element={<AuthSessionProvider><ArchiveScanResultPage /></AuthSessionProvider>}/></Routes></MemoryRouter>);
 await userEvent.click(await screen.findByRole('button',{name:'读取保存建议'}));
 await waitFor(()=>expect(fetchArchiveFindingRepairSuggestions).toHaveBeenCalledWith({job_id:'original-job',document_id:'original-doc',rule_id:'sjtu_rule_18',finding_id:'f1'}));
});
