import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { analyzeDefaultNormativeText, type NormativeIssue } from '../src/api/normativeRules';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/normativeRules', async () => {
  const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
  return {
    ...actual,
    analyzeDefaultNormativeText: vi.fn(),
  };
});

const reqId = 'FEAT-NORMATIVE-FORMAT-RULES';
void reqId;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const scenarioIssues: NormativeIssue[] = [
  {
    rule_id: 'NORM-002',
    category: '标点配对',
    severity: 'high',
    line: 4,
    column: 9,
    excerpt: '未配对（括号',
    message: '圆括号未成对',
    suggestion: '补全或删除未配对的括号',
  },
  {
    rule_id: 'NORM-003',
    category: '重复标点',
    severity: 'medium',
    line: 4,
    column: 15,
    excerpt: '。。',
    message: '存在重复标点',
    suggestion: '保留一个句号',
  },
  {
    rule_id: 'NORM-006',
    category: '文本质量',
    severity: 'medium',
    line: 4,
    column: 17,
    excerpt: '这是一个超过一百二十字符的句子',
    message: '句子超过 120 个字符',
    suggestion: '拆分为更短的句子',
  },
];

function renderRoute(initialPath = '/normative-check') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-NORMATIVE-FORMAT-RULES frontend route and page contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(analyzeDefaultNormativeText).mockReset();
  });

  it('renders /normative-check under the shared auth provider and submits authenticated text through the API client', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(analyzeDefaultNormativeText).mockResolvedValue({ issues: scenarioIssues });
    const user = userEvent.setup();
    const scenarioText = ['摘要', '关键词', '引言', `学生文本包含未配对（括号。。${'问题'.repeat(70)}。`, '结论', '参考文献', '[1] 示例文献'].join('\n');

    renderRoute();

    expect(await screen.findByRole('heading', { name: '默认规范检测规则' })).toBeInTheDocument();
    expect(screen.getByText(/当前登录用户：student01（STUDENT）/)).toBeInTheDocument();

    await user.click(screen.getByLabelText('待检测文本'));
    await user.paste(scenarioText);
    await user.click(screen.getByRole('button', { name: '运行默认规则' }));

    await waitFor(() => expect(analyzeDefaultNormativeText).toHaveBeenCalledWith({ text: scenarioText }));
    expect(await screen.findByText('已返回 3 条问题。')).toBeInTheDocument();

    const table = screen.getByRole('table');
    for (const issue of scenarioIssues) {
      const row = within(table).getByText(issue.rule_id).closest('tr');
      expect(row).toBeTruthy();
      expect(within(row as HTMLTableRowElement).getByText(issue.category)).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(String(issue.line))).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(String(issue.column))).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(issue.message)).toBeInTheDocument();
      expect(within(row as HTMLTableRowElement).getByText(issue.suggestion)).toBeInTheDocument();
    }
  });

  it('renders login-required state for anonymous users and does not run fake local analysis', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute();

    expect(await screen.findByRole('heading', { name: '默认规范检测' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后运行/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(screen.queryByRole('button', { name: '运行默认规则' })).not.toBeInTheDocument();
    expect(analyzeDefaultNormativeText).not.toHaveBeenCalled();
  });

  it('shows an explicit error state and clears stale results when backend analysis fails', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(analyzeDefaultNormativeText)
      .mockResolvedValueOnce({ issues: scenarioIssues })
      .mockRejectedValueOnce(new Error('服务暂不可用'));
    const user = userEvent.setup();

    renderRoute();

    await user.type(await screen.findByLabelText('待检测文本'), '摘要\n关键词\n引言\n问题。。\n结论\n参考文献\n[1] 示例文献');
    await user.click(screen.getByRole('button', { name: '运行默认规则' }));
    expect(await screen.findByText('已返回 3 条问题。')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '运行默认规则' }));

    expect(await screen.findByText('服务暂不可用')).toBeInTheDocument();
    expect(screen.getByText('本次检测未返回问题。')).toBeInTheDocument();
    expect(screen.queryByText('NORM-002')).not.toBeInTheDocument();
  });

  it('uses the shared interceptor-enabled Axios client for normative API calls', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
