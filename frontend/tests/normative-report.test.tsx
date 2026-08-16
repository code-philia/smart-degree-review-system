import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  downloadNormativeReportJson,
  fetchNormativeDetectionHistory,
  fetchNormativeDetectionReport,
  type DetectionTaskResponse,
} from '../src/api/normativeRules';
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
    downloadNormativeReportJson: vi.fn(),
    fetchNormativeDetectionHistory: vi.fn(),
    fetchNormativeDetectionReport: vi.fn(),
  };
});

const REQ_ID = 'FEAT-NORMATIVE-REPORT';
void REQ_ID;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const reportRecord: DetectionTaskResponse = {
  id: 'report-ui-001',
  user_id: 'student01',
  status: 'completed',
  source_type: 'file',
  source_filename: '论文规范检测.txt',
  original_text: ['摘要', '关键词：规范检测', '这一行包含未配对（括号。。', '结论'].join('\n'),
  rule_snapshot: [{ rule_id: 'NORM-002', title: '标点配对' }],
  issues: [
    {
      rule_id: 'NORM-002',
      category: '标点配对',
      severity: 'high',
      line: 3,
      column: 8,
      excerpt: '未配对（括号',
      message: '圆括号未成对',
      suggestion: '补全或删除未配对的括号',
    },
    {
      rule_id: 'NORM-003',
      category: '重复标点',
      severity: 'medium',
      line: 3,
      column: 14,
      excerpt: '。。',
      message: '存在重复标点',
      suggestion: '保留一个句号',
    },
  ],
  severity_counts: { high: 1, medium: 1, low: 0 },
  created_at: '2026-08-04T10:00:00.000Z',
};

function renderRoute(initialPath = '/normative-reports') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-NORMATIVE-REPORT frontend route, page, and client contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchNormativeDetectionHistory).mockReset();
    vi.mocked(fetchNormativeDetectionReport).mockReset();
    vi.mocked(downloadNormativeReportJson).mockReset();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:normative-report');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    vi.spyOn(HTMLElement.prototype, 'click').mockImplementation(() => undefined);
    vi.spyOn(HTMLElement.prototype, 'scrollIntoView').mockImplementation(() => undefined);
    vi.spyOn(window, 'print').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('FEAT-NORMATIVE-REPORT:UI:001 renders login-required state and does not fetch report data for anonymous users', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    renderRoute('/normative-reports');

    expect(await screen.findByRole('heading', { name: '历史检测记录' })).toBeInTheDocument();
    expect(screen.getByText(/请先登录后查看本人检测历史和报告/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(fetchNormativeDetectionHistory).not.toHaveBeenCalled();
    expect(fetchNormativeDetectionReport).not.toHaveBeenCalled();
  });

  it('FEAT-NORMATIVE-REPORT:UI:002 renders runtime history rows with descending records and report actions', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchNormativeDetectionHistory).mockResolvedValue([
      reportRecord,
      {
        ...reportRecord,
        id: 'report-ui-000',
        source_filename: null,
        issues: [],
        severity_counts: { high: 0, medium: 0, low: 0 },
        created_at: '2026-08-03T10:00:00.000Z',
      },
    ]);
    vi.mocked(downloadNormativeReportJson).mockResolvedValue(
      new Blob(['{}'], { type: 'application/json;charset=utf-8' }),
    );
    const user = userEvent.setup();

    renderRoute('/normative-reports');

    expect(await screen.findByRole('heading', { name: '基础规则检测' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '发起检测' })).toHaveAttribute('href', '/normative-check');
    await waitFor(() => expect(fetchNormativeDetectionHistory).toHaveBeenCalledTimes(1));
    const table = await screen.findByRole('table');
    const rows = within(table).getAllByRole('row');
    expect(rows[1]).toHaveTextContent('论文规范检测.txt');
    expect(rows[1]).toHaveTextContent('2');
    expect(rows[1]).toHaveTextContent('1 / 1 / 0');
    expect(rows[1]).toHaveTextContent('2026-08-04 18:00');
    expect(rows[2]).toHaveTextContent('粘贴文本检测');

    await user.click(within(rows[1]).getByRole('button', { name: '报告下载' }));
    expect(downloadNormativeReportJson).toHaveBeenCalledWith('report-ui-001');
    expect(within(rows[1]).getByRole('link', { name: '报告预览' })).toHaveAttribute(
      'href',
      '/normative-reports/report-ui-001',
    );
  });

  it('FEAT-NORMATIVE-REPORT:UI:003 clicks an issue to scroll and highlight its line, then downloads JSON and prints', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchNormativeDetectionReport).mockResolvedValue(reportRecord);
    vi.mocked(downloadNormativeReportJson).mockResolvedValue(
      new Blob([JSON.stringify({ rule_snapshot: reportRecord.rule_snapshot, issues: reportRecord.issues })], {
        type: 'application/json;charset=utf-8',
      }),
    );
    const user = userEvent.setup();

    renderRoute('/normative-reports/report-ui-001');

    expect(await screen.findByRole('heading', { name: '检测报告' })).toBeInTheDocument();
    await waitFor(() => expect(fetchNormativeDetectionReport).toHaveBeenCalledWith('report-ui-001'));
    const issueButton = await screen.findByRole('button', { name: /high 第 3 行，第 8 列/ });
    await user.click(issueButton);

    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
    expect(screen.getByText('这一行包含未配对（括号。。').closest('div')).toHaveClass('bg-yellow-100');

    await user.click(screen.getByRole('button', { name: '下载 UTF-8 JSON' }));
    await waitFor(() => expect(downloadNormativeReportJson).toHaveBeenCalledWith('report-ui-001'));
    expect(URL.createObjectURL).toHaveBeenCalled();

    await user.click(screen.getByRole('button', { name: '浏览器打印' }));
    expect(window.print).toHaveBeenCalled();
  });

  it('FEAT-NORMATIVE-REPORT:API-CLIENT:001 uses shared Axios paths for report history, detail, and blob download', async () => {
    const getSpy = vi.spyOn(apiClient, 'get');
    getSpy.mockResolvedValueOnce({ data: { records: [reportRecord] } });
    getSpy.mockResolvedValueOnce({ data: reportRecord });
    getSpy.mockResolvedValueOnce({ data: new Blob(['{}'], { type: 'application/json' }) });

    const actual = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
    await expect(actual.fetchNormativeDetectionHistory()).resolves.toEqual([reportRecord]);
    await expect(actual.fetchNormativeDetectionReport('report-ui-001')).resolves.toEqual(reportRecord);
    await expect(actual.downloadNormativeReportJson('report-ui-001')).resolves.toBeInstanceOf(Blob);

    expect(getSpy).toHaveBeenNthCalledWith(1, '/normative/detection-reports');
    expect(getSpy).toHaveBeenNthCalledWith(2, '/normative/detection-reports/report-ui-001');
    expect(getSpy).toHaveBeenNthCalledWith(3, '/normative/detection-reports/report-ui-001/download', {
      responseType: 'blob',
      headers: { Accept: 'application/json' },
    });
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
