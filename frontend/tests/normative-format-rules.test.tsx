import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import apiClient from '../src/api';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { fetchReviewPilotPaperLintRules, runReviewPilotPaperLint } from '../src/api/paperLint';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return { ...actual, fetchCurrentSession: vi.fn() };
});

vi.mock('../src/api/paperLint', async () => {
  const actual = await vi.importActual<typeof import('../src/api/paperLint')>('../src/api/paperLint');
  return {
    ...actual,
    fetchReviewPilotPaperLintRules: vi.fn(),
    runReviewPilotPaperLint: vi.fn(),
  };
});

vi.mock('../src/components/paperLint/Workspace', () => ({
  PaperLintWorkspace: ({ findings }: { findings: Array<{ finding: { message: string } }> }) => (
    <div data-testid="paper-lint-workspace">{findings.map((item) => item.finding.message).join('；')}</div>
  ),
}));

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const catalog = {
  engine: 'review-pilot',
  mode: 'pdf_lint',
  semantic_model: 'deepseek-v4-flash',
  rules: [
    {
      rule_id: 'chinese_title_format_check',
      title: '中文论文题名格式',
      description: '检查中文论文题名页版式。',
      default_severity: 'warning' as const,
      default_enabled: true,
      execution_mode: 'deterministic' as const,
      uses_external_model: false,
      available: true,
    },
    {
      rule_id: 'toc_format_check',
      title: '目录格式',
      description: '检查目录标题、条目、缩进和页码对齐。',
      default_severity: 'warning' as const,
      default_enabled: true,
      execution_mode: 'deterministic' as const,
      uses_external_model: false,
      available: true,
    },
    {
      rule_id: 'bilingual_abstract_consistency_check',
      title: '中英文摘要内容一致性',
      description: '使用 DeepSeek 检查摘要内容。',
      default_severity: 'warning' as const,
      default_enabled: false,
      execution_mode: 'semantic' as const,
      uses_external_model: true,
      available: true,
    },
  ],
};

const completedResponse = {
  source_filename: '论文.pdf',
  selected_rule_ids: catalog.rules.map((rule) => rule.rule_id),
  processed_at: '2026-08-06T08:00:00.000Z',
  result: {
    type: 'paper_lint' as const,
    paper_title: '测试论文',
    ruleset: {
      id: 'review-pilot-pdf-lint',
      name: 'review-pilot PDF 规则',
      version_number: 1,
      version_label: '当前部署版本',
    },
    rule_runs: [
      {
        rule_run_id: 'run-1',
        rule_id: 'chinese_title_format_check',
        severity: 'warning' as const,
        execution_status: 'completed' as const,
        evidence_mode: 'derived' as const,
        outcome: 'issues_found' as const,
        message: null,
        findings: [
          {
            finding_id: 'finding-1',
            rule_id: 'chinese_title_format_check',
            message: '中文论文标题应居中。',
            suggestion: '将标题水平居中。',
            location: {
              type: 'pdf_bbox' as const,
              page_number: 1,
              bounding_rect: { x1: 10, y1: 20, x2: 100, y2: 40, width: 595, height: 842, page_number: 1 },
              rects: [],
              text_excerpt: '测试论文',
            },
            anchors: [],
          },
        ],
      },
    ],
    summary: {
      rule_count: 2,
      completed_rule_count: 2,
      unsupported_rule_count: 0,
      error_rule_count: 0,
      issue_rule_count: 1,
      finding_count: 1,
      error_finding_count: 0,
      warning_finding_count: 1,
      info_finding_count: 0,
      derived_rule_count: 2,
    },
  },
};

function renderRoute() {
  return render(
    <MemoryRouter initialEntries={['/normative-check']}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('review-pilot PDF rules review route', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchReviewPilotPaperLintRules).mockReset();
    vi.mocked(runReviewPilotPaperLint).mockReset();
  });

  it('loads default rules, uploads a PDF and renders the real API result', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue(catalog);
    vi.mocked(runReviewPilotPaperLint).mockResolvedValue(completedResponse);
    const user = userEvent.setup();
    const pdf = new File(['%PDF-1.7\n'], '论文.pdf', { type: 'application/pdf' });

    renderRoute();

    expect(await screen.findByRole('heading', { name: 'PDF 论文规则审查' })).toBeInTheDocument();
    expect(await screen.findByText('中文论文题名格式')).toBeInTheDocument();
    expect(screen.getByText('目录格式')).toBeInTheDocument();
    await user.upload(screen.getByLabelText('上传待审查 PDF'), pdf);
    await user.click(screen.getByRole('button', { name: '开始规则审查' }));

    await waitFor(() =>
      expect(runReviewPilotPaperLint).toHaveBeenCalledWith(
        pdf,
        ['chinese_title_format_check', 'toc_format_check'],
        false,
      ),
    );
    expect(await screen.findByText('发现 1 项问题')).toBeInTheDocument();
    expect(screen.getByTestId('paper-lint-workspace')).toHaveTextContent('中文论文标题应居中。');
  });

  it('warns before sending selected semantic evidence to DeepSeek', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue(catalog);
    vi.mocked(runReviewPilotPaperLint).mockResolvedValue(completedResponse);
    const user = userEvent.setup();
    const pdf = new File(['%PDF-1.7\n'], '论文.pdf', { type: 'application/pdf' });

    renderRoute();

    const semanticRule = await screen.findByRole('checkbox', { name: /中英文摘要内容一致性/ });
    await user.upload(screen.getByLabelText('上传待审查 PDF'), pdf);
    await user.click(semanticRule);

    expect(screen.getByRole('note')).toHaveTextContent('发送到 DeepSeek 官方 API');
    expect(screen.getByRole('button', { name: '开始规则审查' })).toBeDisabled();
    await user.click(screen.getByRole('checkbox', { name: /我确认该论文相关文本允许发送/ }));
    expect(screen.getByRole('button', { name: '开始规则审查' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: '开始规则审查' }));
    await waitFor(() =>
      expect(runReviewPilotPaperLint).toHaveBeenCalledWith(
        pdf,
        ['chinese_title_format_check', 'toc_format_check', 'bilingual_abstract_consistency_check'],
        true,
      ),
    );
  });

  it('requires login and never loads the engine catalog for an anonymous user', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: 'PDF 论文规则审查' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后上传论文/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(fetchReviewPilotPaperLintRules).not.toHaveBeenCalled();
  });

  it('rejects non-PDF input in the page before invoking the backend', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchReviewPilotPaperLintRules).mockResolvedValue(catalog);

    renderRoute();
    await screen.findByText('中文论文题名格式');
    fireEvent.change(screen.getByLabelText('上传待审查 PDF'), {
      target: { files: [new File(['plain text'], '论文.txt', { type: 'text/plain' })] },
    });

    expect(await screen.findByText('仅支持上传 PDF 文件')).toBeInTheDocument();
    expect(runReviewPilotPaperLint).not.toHaveBeenCalled();
  });

  it('uses the shared interceptor-enabled Axios client', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
