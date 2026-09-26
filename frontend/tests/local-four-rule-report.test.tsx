import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import PaperLintReportPage from '../src/pages/PaperLintReportPage';
import { fetchPaperLintReport, fetchPaperLintReportPdf, fetchReviewPilotPaperLintRules,
  type PaperLintRunResponse } from '../src/api/paperLint';

vi.mock('../src/api/paperLint', async () => {
  const actual = await vi.importActual<typeof import('../src/api/paperLint')>('../src/api/paperLint');
  return { ...actual, fetchPaperLintReport: vi.fn(), fetchPaperLintReportPdf: vi.fn(),
    fetchReviewPilotPaperLintRules: vi.fn() };
});
vi.mock('../src/components/paperLint/Workspace', () => ({ PaperLintWorkspace: () => <div>PDF 工作区</div> }));

const report: PaperLintRunResponse = {
  id: 'report-24', source_filename: '待检论文.pdf', selected_rule_ids: ['sjtu_rule_24'],
  created_at: '2026-09-26T04:30:00.000Z',
  summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0,
    info_finding_count: 0, rule_count: 1, unsupported_rule_count: 1, error_rule_count: 0, ruleset_label: '本地四规则' },
  result: {
    type: 'paper_lint', paper_title: '上传论文',
    ruleset: { id: 'sjtu-four-rule-pdf', name: '上交大本地四规则', version_number: 1, version_label: '本地四规则' },
    rule_runs: [{ rule_run_id: 'run_sjtu_rule_24', rule_id: 'sjtu_rule_24', severity: 'warning',
      execution_status: 'unsupported', evidence_mode: 'unsupported', outcome: 'inconclusive',
      message: '无法识别参考文献表', findings: [] }],
    summary: { rule_count: 1, completed_rule_count: 0, unsupported_rule_count: 1,
      error_rule_count: 0, issue_rule_count: 0, finding_count: 0, error_finding_count: 0,
      warning_finding_count: 0, info_finding_count: 0, derived_rule_count: 0 },
  },
};

describe('saved local four-rule PDF report', () => {
  it('shows the source filename and unsupported reason instead of claiming a pass', async () => {
    vi.mocked(fetchPaperLintReport).mockResolvedValue(report);
    vi.mocked(fetchPaperLintReportPdf).mockResolvedValue(new Blob(['%PDF-1.7\n'], { type: 'application/pdf' }));
    vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue({
      engine: 'sjtu-local', mode: 'pdf_lint', semantic_model: 'deepseek-v4-flash',
      rules: [{ rule_id: 'sjtu_rule_24', title: '规则 24 · 参考文献未被全文引用',
        description: '全文引用检查', default_severity: 'warning', default_enabled: false,
        execution_mode: 'deterministic', uses_external_model: false, available: true, source: 'sjtu-local' }],
    });
    render(<MemoryRouter initialEntries={['/normative-reports/pdf/report-24']}>
      <Routes><Route path="/normative-reports/pdf/:reportId" element={<PaperLintReportPage />} /></Routes>
    </MemoryRouter>);
    expect(await screen.findByRole('heading', { name: '待检论文.pdf' })).toBeInTheDocument();
    expect(screen.getByText('部分规则无法判定')).toBeInTheDocument();
    expect(screen.getByText('无法识别参考文献表')).toBeInTheDocument();
  });
});