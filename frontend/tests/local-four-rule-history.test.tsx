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
    vi.mocked(fetchPaperLintReports).mockResolvedValue([
      {
        id: 'unsupported-24',
        source_filename: '待检论文.pdf',
        selected_rule_ids: ['sjtu_rule_24'],
        created_at: '2026-09-26T04:30:00.000Z',
        summary: {
          finding_count: 0,
          error_finding_count: 0,
          warning_finding_count: 0,
          info_finding_count: 0,
          rule_count: 1,
          unsupported_rule_count: 1,
          error_rule_count: 0,
          ruleset_label: '本地四规则',
        },
      },
    ]);
    render(
      <MemoryRouter initialEntries={['/normative-reports']}>
        <Routes>
          <Route path="/normative-reports" element={<NormativeReportPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText('待检论文.pdf')).toBeInTheDocument();
    expect(screen.getByText('部分规则无法判定')).toBeInTheDocument();
    expect(screen.queryByText('未发现问题')).not.toBeInTheDocument();
  });

  it('keeps local PDF reports inside the 30-rule history and excludes basic reports', async () => {
    vi.mocked(fetchPaperLintReports).mockResolvedValue([
      {
        id: 'local-24',
        source_filename: '四规则论文.pdf',
        selected_rule_ids: ['sjtu_rule_24'],
        created_at: '2026-09-26T04:30:00.000Z',
        summary: {
          finding_count: 0,
          error_finding_count: 0,
          warning_finding_count: 0,
          info_finding_count: 0,
          rule_count: 1,
          unsupported_rule_count: 0,
          error_rule_count: 0,
          ruleset_label: '本地四规则',
        },
      },
      {
        id: 'basic-1',
        source_filename: '基础规则论文.pdf',
        selected_rule_ids: ['toc_format_check'],
        created_at: '2026-09-26T04:00:00.000Z',
        summary: {
          finding_count: 0,
          error_finding_count: 0,
          warning_finding_count: 0,
          info_finding_count: 0,
          rule_count: 1,
          unsupported_rule_count: 0,
          error_rule_count: 0,
          ruleset_label: '基础规则',
        },
      },
      {
        id: 'keyword-36',
        source_filename: '关键词规则论文.pdf',
        selected_rule_ids: ['keyword_count_check'],
        created_at: '2026-09-26T05:00:00.000Z',
        summary: {
          finding_count: 1,
          error_finding_count: 0,
          warning_finding_count: 1,
          info_finding_count: 0,
          rule_count: 1,
          unsupported_rule_count: 0,
          error_rule_count: 0,
          ruleset_label: '本地规则',
        },
      },
      {
        id: 'abstract-object-37',
        source_filename: '摘要编号论文.pdf',
        selected_rule_ids: ['abstract_object_number_check'],
        created_at: '2026-09-26T05:10:00.000Z',
        summary: {
          finding_count: 1,
          error_finding_count: 0,
          warning_finding_count: 1,
          info_finding_count: 0,
          rule_count: 1,
          unsupported_rule_count: 0,
          error_rule_count: 0,
          ruleset_label: '本地规则',
        },
      },
    ]);
    render(
      <MemoryRouter initialEntries={['/thirty-rules-check/reports']}>
        <Routes>
          <Route path="/thirty-rules-check/reports" element={<NormativeReportPage mode="thirty" />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText('四规则论文.pdf')).toBeInTheDocument();
    expect(await screen.findByText('关键词规则论文.pdf')).toBeInTheDocument();
    expect(await screen.findByText('摘要编号论文.pdf')).toBeInTheDocument();
    expect(screen.queryByText('基础规则论文.pdf')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '发起检测' })).toHaveAttribute('href', '/thirty-rules-check');
    expect(
      screen.getAllByRole('link', { name: '继续处理' }).map((link) => link.getAttribute('href')),
    ).toEqual(
      expect.arrayContaining([
        '/thirty-rules-check/reports/pdf/local-24',
        '/thirty-rules-check/reports/pdf/keyword-36',
        '/thirty-rules-check/reports/pdf/abstract-object-37',
      ]),
    );
  });
});
