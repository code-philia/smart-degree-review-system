import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import apiClient from '../src/api';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  createDuplicationDetection,
  fetchDuplicationDetectionReport,
  type DuplicationDetectionResponse,
  type DuplicationHistoryRecord,
} from '../src/api/normativeRules';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';

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
    createDuplicationDetection: vi.fn(),
    fetchDuplicationDetectionReport: vi.fn(),
  };
});

const reqId = 'FEAT-DUPLICATION-DETECT';
void reqId;

const student: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

function renderDetectRoute() {
  return render(
    <MemoryRouter initialEntries={['/duplication-detect']}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

function renderHistoryReportRoute() {
  return render(
    <MemoryRouter initialEntries={['/duplication-history/report-001']}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

function report(overrides: Partial<DuplicationDetectionResponse> = {}): DuplicationDetectionResponse {
  return {
    status: 'completed',
    detection_type: 'campus_corpus',
    detection_type_label: '校内库查重',
    detection_description: '与当前试点本地样本库进行相似片段比对。',
    source_type: 'paste',
    source_filename: null,
    threshold: 0.65,
    effective_character_count: 120,
    total_similarity_rate: 0.42,
    sample_count: 1,
    top_matches: [
      {
        sample_id: 'sample-001',
        title: '高校数字治理样本',
        subject: '管理学',
        year: 2024,
        jaccard_score: 0.812,
        matched_character_count: 52,
        segments: [
          {
            source_start: 10,
            source_end: 62,
            sample_start: 0,
            sample_end: 52,
            source_excerpt: '高校数字治理平台的建设效果进行分析',
            sample_excerpt: '高校数字治理平台的建设效果进行分析',
          },
        ],
      },
    ],
    risk: {
      score: 37,
      label: 'heuristic_only',
      explanation: '写作风险分是启发式风险提示，并非 AI 真伪结论。',
      factors: {
        paragraph_duplication_rate: 20,
        sentence_length_low_variation: 40,
        template_connector_density: 30,
        vague_phrase_density: 70,
      },
      weights: {
        paragraph_duplication_rate: 0.35,
        sentence_length_low_variation: 0.25,
        template_connector_density: 0.2,
        vague_phrase_density: 0.2,
      },
    },
    ...overrides,
  };
}

function fileInput(container: HTMLElement) {
  const input = container.querySelector('input[type="file"]');
  expect(input).toBeInstanceOf(HTMLInputElement);
  return input as HTMLInputElement;
}

function testFileList(file: File): FileList {
  return {
    0: file,
    length: 1,
    item: (index: number) => (index === 0 ? file : null),
    [Symbol.iterator]: function* iterateFiles() {
      yield file;
    },
  } as FileList;
}

describe('FEAT-DUPLICATION-DETECT frontend page route and API client contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(createDuplicationDetection).mockReset();
    vi.mocked(fetchDuplicationDetectionReport).mockReset();
  });

  it('FEAT-DUPLICATION-HISTORY:UI:REPORT:001 presents structured report details instead of raw JSON', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });
    const detectionReport = report();
    const historyRecord: DuplicationHistoryRecord = {
      id: 'report-001',
      user_id: student.username,
      source_type: 'paste',
      source_filename: null,
      original_text: '待检测论文文本',
      total_similarity_rate: detectionReport.total_similarity_rate,
      writing_risk_score: detectionReport.risk.score,
      sample_count: detectionReport.sample_count,
      report_json: detectionReport,
      created_at: '2026-08-15T07:00:00.000Z',
    };
    vi.mocked(fetchDuplicationDetectionReport).mockResolvedValue(historyRecord);

    renderHistoryReportRoute();

    expect(await screen.findByRole('heading', { name: '检测摘要' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '相似片段' })).toBeInTheDocument();
    expect(screen.getByText('高校数字治理样本')).toBeInTheDocument();
    expect(screen.getByText('论文片段')).toBeInTheDocument();
    expect(screen.getByText('样本片段')).toBeInTheDocument();
    expect(screen.queryByText('"top_matches"')).not.toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-DETECT:UI:AUTH:001 renders shared-session anonymous login prompt instead of local fake detection controls', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValueOnce({ response: { status: 401 } });

    renderDetectRoute();

    expect(await screen.findByText(/请先登录后发起相似度与写作风险检测/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(screen.queryByRole('button', { name: '检测' })).not.toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-DETECT:UI:ROUTE:001 mounts /duplication-detect under the app route tree with the upload workflow', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });

    renderDetectRoute();

    expect(await screen.findByRole('heading', { name: '发起检测' })).toBeInTheDocument();
    expect(screen.getByText('选择论文文件')).toBeInTheDocument();
    expect(screen.getByRole('combobox')).toHaveValue('campus_corpus');
    expect(screen.getByRole('option', { name: '校内库查重' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'AIGC 写作风险检测' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '开始检测' })).toBeDisabled();
  });

  it('FEAT-DUPLICATION-DETECT:UI:FILE:001 reads accepted UTF-8 files, rejects unsupported files, and submits file metadata through the API', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });
    vi.mocked(createDuplicationDetection).mockResolvedValue(
      report({ source_type: 'file', source_filename: 'paper.md' }),
    );
    const user = userEvent.setup();
    const { container } = renderDetectRoute();

    await screen.findByRole('heading', { name: '发起检测' });
    fireEvent.change(fileInput(container), {
      target: { files: testFileList(new File(['DOCX'], 'paper.docx')) },
    });
    expect(await screen.findByText('仅支持上传 .txt、.md 或 .pdf 文件')).toBeInTheDocument();
    expect(createDuplicationDetection).not.toHaveBeenCalled();

    await user.upload(
      fileInput(container),
      new File(['高校数字治理平台的建设效果进行分析'], 'paper.md', { type: 'text/markdown' }),
    );
    await waitFor(() => expect(screen.getByDisplayValue('高校数字治理平台的建设效果进行分析')).toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '开始检测' }));

    await waitFor(() =>
      expect(createDuplicationDetection).toHaveBeenCalledWith({
        text: '高校数字治理平台的建设效果进行分析',
        source_type: 'file',
        source_filename: 'paper.md',
        detection_type: 'campus_corpus',
      }),
    );
  });

  it('FEAT-DUPLICATION-DETECT:SCENARIO:001 submits pasted text and displays sample hit, Jaccard score, total similarity rate, and heuristic-risk disclaimer', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });
    vi.mocked(createDuplicationDetection).mockResolvedValue(report());
    const user = userEvent.setup();

    renderDetectRoute();

    await user.type(await screen.findByPlaceholderText(/粘贴待检测论文文本/), '高校数字治理平台的建设效果进行分析');
    await user.click(screen.getByRole('button', { name: '开始检测' }));

    await waitFor(() =>
      expect(createDuplicationDetection).toHaveBeenCalledWith({
        text: '高校数字治理平台的建设效果进行分析',
        source_type: 'paste',
        source_filename: null,
        detection_type: 'campus_corpus',
      }),
    );
    expect(await screen.findByText(/写作风险分为启发式风险提示，并非 AI 真伪结论/)).toBeInTheDocument();
    expect(screen.getByText('比对样本数').parentElement).toHaveTextContent('1');
    expect(screen.getByText('总相似率').parentElement).toHaveTextContent('42%');
    expect(screen.getByRole('heading', { name: '高校数字治理样本' })).toBeInTheDocument();
    expect(screen.getByText(/Jaccard：0.812 · 命中字符：52/)).toBeInTheDocument();
    expect(screen.getByText(/高校数字治理平台的建设效果进行分析/)).toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-DETECT:UI:TYPE:001 submits AIGC writing-risk mode and does not present corpus matches as its result', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });
    vi.mocked(createDuplicationDetection).mockResolvedValue(
      report({
        detection_type: 'aigc_writing_risk',
        detection_type_label: 'AIGC 写作风险检测',
        detection_description: '依据文本特征生成写作风险提示，不构成 AI 生成真伪结论。',
        sample_count: 0,
        top_matches: [],
      }),
    );
    const user = userEvent.setup();

    renderDetectRoute();

    await user.selectOptions(await screen.findByRole('combobox'), 'aigc_writing_risk');
    await user.type(
      screen.getByPlaceholderText(/粘贴待检测论文文本/),
      '首先，本文从多个方面进行分析。因此，相关问题具有重要意义。',
    );
    await user.click(screen.getByRole('button', { name: '开始检测' }));

    await waitFor(() =>
      expect(createDuplicationDetection).toHaveBeenCalledWith(
        expect.objectContaining({ detection_type: 'aigc_writing_risk' }),
      ),
    );
    expect(await screen.findByRole('heading', { name: 'AIGC 写作风险检测' })).toBeInTheDocument();
    expect(screen.getByText('写作风险分')).toBeInTheDocument();
    expect(screen.queryByText('相似片段')).not.toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-DETECT:SCENARIO:002 renders no_samples explicitly without fabricated match rows while still showing writing risk', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });
    vi.mocked(createDuplicationDetection).mockResolvedValue(
      report({
        status: 'no_samples',
        sample_count: 0,
        total_similarity_rate: 0,
        top_matches: [],
        risk: { ...report().risk, score: 28 },
      }),
    );
    const user = userEvent.setup();

    renderDetectRoute();

    await user.type(await screen.findByPlaceholderText(/粘贴待检测论文文本/), '无样本时也需要计算写作风险');
    await user.click(screen.getByRole('button', { name: '开始检测' }));

    expect(await screen.findByText('当前样本库没有可用比对样本，因此未生成相似片段。')).toBeInTheDocument();
    expect(screen.getByText('比对样本数').parentElement).toHaveTextContent('0');
    expect(screen.getByText('总相似率').parentElement).toHaveTextContent('0%');
    expect(screen.getByText('风险分').parentElement).toHaveTextContent('28');
    expect(screen.queryByRole('heading', { name: '硬编码样本' })).not.toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-DETECT:API-CLIENT:001 posts through the shared same-origin Axios client to the duplication detection endpoint', async () => {
    const postSpy = vi
      .spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: report({ status: 'no_samples', sample_count: 0, top_matches: [] }) });
    const realApi = await vi.importActual<typeof import('../src/api/normativeRules')>('../src/api/normativeRules');
    const payload = {
      text: '客户端提交待检文本',
      source_type: 'paste' as const,
      source_filename: null,
      threshold: 0.65,
      detection_type: 'campus_corpus' as const,
    };

    await expect(realApi.createDuplicationDetection(payload)).resolves.toMatchObject({ status: 'no_samples' });

    expect(postSpy).toHaveBeenCalledWith('/normative/duplication-detections', payload, { timeout: 310_000 });
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
    postSpy.mockRestore();
  });
});
