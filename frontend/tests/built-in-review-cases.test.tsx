import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import {
  fetchPaperLintBuiltInCase,
  fetchPaperLintBuiltInCasePdf,
  fetchPaperLintBuiltInCases,
  type PaperLintBuiltInCase,
} from '../src/api/paperLint';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return { ...actual, fetchCurrentSession: vi.fn() };
});

vi.mock('../src/api/paperLint', async () => {
  const actual = await vi.importActual<typeof import('../src/api/paperLint')>('../src/api/paperLint');
  return {
    ...actual,
    fetchPaperLintBuiltInCases: vi.fn(),
    fetchPaperLintBuiltInCase: vi.fn(),
    fetchPaperLintBuiltInCasePdf: vi.fn(),
  };
});

vi.mock('../src/components/paperLint/Workspace', () => ({
  PaperLintWorkspace: ({ file, findings }: { file: File; findings: Array<{ finding: { message: string } }> }) => (
    <div data-testid="paper-lint-workspace">
      <span>{file.name}</span>
      <span>{findings.map((item) => item.finding.message).join('；')}</span>
    </div>
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

const reviewCase: PaperLintBuiltInCase = {
  id: 'yandex-accuracy-claim-evidence',
  title: '跨页数值论点与实验论据不一致',
  description: '研究内容声称 Yandex 准确率为 80.0%，实验结果报告为 60.5%。',
  pdf_filename: '内置案例-论点与论据一致性.pdf',
  claim_page: 22,
  evidence_page: 57,
  rule: {
    rule_id: 'claim_evidence_inconsistency_check',
    title: '论点与论据一致性',
    description: '检查论文中的数值论点与候选实验论据是否矛盾。',
    default_severity: 'warning',
    default_enabled: true,
    execution_mode: 'semantic',
    uses_external_model: true,
    available: true,
  },
  result: {
    type: 'paper_lint',
    paper_title: '零标注样本的文本验证码识别方法研究',
    ruleset: { id: 'built-in-review-case', name: '内置审查案例', version_number: 1, version_label: '案例 1' },
    rule_runs: [
      {
        rule_run_id: 'run-1',
        rule_id: 'claim_evidence_inconsistency_check',
        severity: 'warning',
        execution_status: 'completed',
        evidence_mode: 'derived',
        outcome: 'issues_found',
        findings: [
          {
            finding_id: 'finding-1',
            rule_id: 'claim_evidence_inconsistency_check',
            message: '80.0% 与实验结果 60.5% 不一致。',
            suggestion: '将论点修正为 60.5%。',
            location: { type: 'pdf_page', page_number: 22, text_excerpt: '准确率为80.0%。' },
            anchors: [
              {
                anchor_id: 'claim-1',
                role: 'claim',
                label: '论点（第 22 页）',
                location: { type: 'pdf_page', page_number: 22, text_excerpt: '80.0%' },
              },
              {
                anchor_id: 'evidence-1',
                role: 'evidence',
                label: '论据（第 57 页）',
                location: { type: 'pdf_page', page_number: 57, text_excerpt: '60.5%' },
              },
            ],
          },
        ],
      },
    ],
    summary: {
      rule_count: 1,
      completed_rule_count: 1,
      unsupported_rule_count: 0,
      error_rule_count: 0,
      issue_rule_count: 1,
      finding_count: 1,
      error_finding_count: 0,
      warning_finding_count: 1,
      info_finding_count: 0,
      derived_rule_count: 1,
    },
  },
};

function renderRoute(path = '/review-cases') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('built-in review cases module', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchPaperLintBuiltInCases).mockReset();
    vi.mocked(fetchPaperLintBuiltInCase).mockReset();
    vi.mocked(fetchPaperLintBuiltInCasePdf).mockReset();
  });

  it('opens the deterministic case from the catalog and renders its PDF workspace result', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchPaperLintBuiltInCases).mockResolvedValue({
      cases: [
        { ...reviewCase, finding_count: 1 },
        {
          ...reviewCase,
          id: 'bilingual-abstract-content-mismatch',
          title: '中英文摘要研究内容不一致',
          description: '中文摘要讨论遥感影像分割，英文摘要讨论验证码识别，研究内容明显不一致。',
          claim_page: 7,
          evidence_page: 9,
          rule: {
            ...reviewCase.rule,
            rule_id: 'bilingual_abstract_consistency_check',
            title: '中英文摘要内容一致性',
          },
        },
      ],
    });
    vi.mocked(fetchPaperLintBuiltInCase).mockResolvedValue(reviewCase);
    vi.mocked(fetchPaperLintBuiltInCasePdf).mockResolvedValue(new Blob(['%PDF-1.7\n'], { type: 'application/pdf' }));
    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByRole('heading', { name: '内置审查案例' })).toBeInTheDocument();
    expect(screen.getByText('跨页数值论点与实验论据不一致')).toBeInTheDocument();
    expect(screen.getByText('中英文摘要研究内容不一致')).toBeInTheDocument();
    expect(screen.getByText('第 22 页')).toBeInTheDocument();
    expect(screen.getByText('第 57 页')).toBeInTheDocument();
    await user.click(screen.getAllByRole('link', { name: '查看案例' })[0]);

    expect(await screen.findByRole('heading', { name: '跨页数值论点与实验论据不一致' })).toBeInTheDocument();
    expect(screen.getByTestId('paper-lint-workspace')).toHaveTextContent('内置案例-论点与论据一致性.pdf');
    expect(screen.getByTestId('paper-lint-workspace')).toHaveTextContent('80.0% 与实验结果 60.5% 不一致');
    expect(screen.queryByRole('button', { name: /重新运行/ })).not.toBeInTheDocument();
  });

  it('requires login without requesting case data', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByText('请先登录后查看案例')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(fetchPaperLintBuiltInCases).not.toHaveBeenCalled();
  });
});
