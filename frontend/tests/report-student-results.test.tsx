import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  downloadStudentReportResultJson,
  fetchStudentReportResultDetail,
  fetchStudentReportResults,
  type StudentReportResultDetail,
  type StudentReportResultSummary,
} from '../src/api/reportStudentResults';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/reportStudentResults', async () => {
  const actual = await vi.importActual<typeof import('../src/api/reportStudentResults')>('../src/api/reportStudentResults');
  return {
    ...actual,
    downloadStudentReportResultJson: vi.fn(),
    fetchStudentReportResultDetail: vi.fn(),
    fetchStudentReportResults: vi.fn(),
  };
});

const REQ_ID = 'FEAT-REPORT-STUDENT-RESULTS';
void REQ_ID;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const listResults: StudentReportResultSummary[] = [
  {
    submission_id: 'student-result-newer',
    batch_id: 'student-result-batch-001',
    source_type: 'normative',
    report_id: 'normative-feedback-report',
    status: 'review_completed_feedback',
    submitted_at: '2026-08-05T12:00:00.000Z',
    feedback_at: '2026-08-05T13:00:00.000Z',
  },
  {
    submission_id: 'student-result-viewed',
    batch_id: 'student-result-batch-002',
    source_type: 'ai_review',
    report_id: 'ai-feedback-report',
    status: 'student_viewed_feedback',
    submitted_at: '2026-08-04T12:00:00.000Z',
    feedback_at: '2026-08-04T13:00:00.000Z',
  },
];

const detailResult: StudentReportResultDetail = {
  ...listResults[0],
  status: 'student_viewed_feedback',
  report: {
    title: 'normative-feedback-report',
    original_text: '原报告正文：学生提交的完整文本。',
    findings: [{ id: 'finding-001', title: '格式问题', severity: 'medium', excerpt: '问题片段' }],
    severity_counts: { medium: 1 },
    created_at: '2026-08-05T12:00:00.000Z',
  },
  review: {
    annotations: [{ finding_id: 'finding-001', comment: '请补充该 finding 的定位依据。' }],
    overall_evaluation: '整体评价：本轮报告已完成批阅。',
    improvement_suggestions: '整改建议：下一轮提交前逐条回复批注。',
    submitted_at: '2026-08-05T13:00:00.000Z',
  },
  history_rounds: listResults,
};

function renderRoute(initialPath = '/student-report-results') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

describe('FEAT-REPORT-STUDENT-RESULTS frontend page and client contract', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchStudentReportResults).mockReset();
    vi.mocked(fetchStudentReportResultDetail).mockReset();
    vi.mocked(downloadStudentReportResultJson).mockReset();
  });

  it('FEAT-REPORT-STUDENT-RESULTS:UI:LIST-FILTERS:001 renders runtime result rows and refetches through time, report type, and status filters', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchStudentReportResults).mockResolvedValue({ results: listResults });
    const user = userEvent.setup();

    renderRoute();

    expect(await screen.findByRole('heading', { name: '我的批阅结果' })).toBeInTheDocument();
    const list = screen.getByRole('list', { name: '批阅结果列表' });
    expect(within(list).getByText('normative-feedback-report')).toBeInTheDocument();
    expect(within(list).getByText('ai-feedback-report')).toBeInTheDocument();
    expect(screen.queryByText(/示例|demo|fake/i)).not.toBeInTheDocument();
    expect(fetchStudentReportResults).toHaveBeenCalledWith({});

    await user.type(screen.getByLabelText('开始时间'), '2026-08-05');
    await user.type(screen.getByLabelText('结束时间'), '2026-08-06');
    await user.selectOptions(screen.getByLabelText('报告类型'), 'normative');
    await user.selectOptions(screen.getByLabelText('状态'), 'review_completed_feedback');

    await waitFor(() => expect(fetchStudentReportResults).toHaveBeenLastCalledWith({
      from: '2026-08-05',
      to: '2026-08-06',
      source_type: 'normative',
      status: 'review_completed_feedback',
    }));
  });

  it('FEAT-REPORT-STUDENT-RESULTS:UI:SCENARIO:001 renders original report, annotations, overall evaluation, suggestions, history, and viewed status from detail open', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchStudentReportResultDetail).mockResolvedValue(detailResult);

    renderRoute('/student-report-results/student-result-newer');

    expect(await screen.findByRole('heading', { name: 'normative-feedback-report' })).toBeInTheDocument();
    expect(screen.getByText('状态：student_viewed_feedback')).toBeInTheDocument();
    expect(screen.getByText('原报告正文：学生提交的完整文本。')).toBeInTheDocument();
    expect(screen.getByText('请补充该 finding 的定位依据。')).toBeInTheDocument();
    expect(screen.getByText('整体评价：本轮报告已完成批阅。')).toBeInTheDocument();
    expect(screen.getByText('整改建议：下一轮提交前逐条回复批注。')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: '历史轮次' })).toHaveTextContent('ai-feedback-report');
    expect(fetchStudentReportResultDetail).toHaveBeenCalledWith('student-result-newer');
  });

  it('FEAT-REPORT-STUDENT-RESULTS:UI:DOWNLOAD:001 invokes the real JSON download client for the selected submission and surfaces completion', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(fetchStudentReportResultDetail).mockResolvedValue(detailResult);
    vi.mocked(downloadStudentReportResultJson).mockResolvedValue({
      submission_id: 'student-result-newer',
      report_summary: listResults[0],
      annotations: detailResult.review.annotations,
      overall_evaluation: detailResult.review.overall_evaluation,
      improvement_suggestions: detailResult.review.improvement_suggestions,
    });
    const user = userEvent.setup();

    renderRoute('/student-report-results/student-result-newer');
    await screen.findByRole('heading', { name: 'normative-feedback-report' });
    await user.click(screen.getByRole('button', { name: '下载 JSON' }));

    expect(downloadStudentReportResultJson).toHaveBeenCalledWith('student-result-newer');
    expect(await screen.findByText('JSON 文件已准备，可保存本轮摘要、批注和评价。')).toBeInTheDocument();
  });

  it('FEAT-REPORT-STUDENT-RESULTS:API-CLIENT:001 uses shared Axios params and encoded detail/download URLs', async () => {
    const getSpy = vi.spyOn(apiClient, 'get');
    getSpy
      .mockResolvedValueOnce({ data: { results: listResults } })
      .mockResolvedValueOnce({ data: detailResult })
      .mockResolvedValueOnce({ data: {
        submission_id: 'student result/newer',
        report_summary: listResults[0],
        annotations: detailResult.review.annotations,
        overall_evaluation: detailResult.review.overall_evaluation,
        improvement_suggestions: detailResult.review.improvement_suggestions,
      } });

    const actual = await vi.importActual<typeof import('../src/api/reportStudentResults')>('../src/api/reportStudentResults');
    await expect(actual.fetchStudentReportResults({ from: '2026-08-05', source_type: 'normative', status: 'review_completed_feedback' }))
      .resolves.toEqual({ results: listResults });
    await expect(actual.fetchStudentReportResultDetail('student result/newer')).resolves.toEqual(detailResult);
    await expect(actual.downloadStudentReportResultJson('student result/newer')).resolves.toMatchObject({ submission_id: 'student result/newer' });

    expect(getSpy).toHaveBeenNthCalledWith(1, '/normative/student-report-results', {
      params: { from: '2026-08-05', source_type: 'normative', status: 'review_completed_feedback' },
    });
    expect(getSpy).toHaveBeenNthCalledWith(2, '/normative/student-report-results/student%20result%2Fnewer');
    expect(getSpy).toHaveBeenNthCalledWith(3, '/normative/student-report-results/student%20result%2Fnewer/download');
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
