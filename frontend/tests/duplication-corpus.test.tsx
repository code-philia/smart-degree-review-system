import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import {
  createDuplicationCorpusSample,
  deleteDuplicationCorpusSample,
  fetchDuplicationCorpusSamples,
  type DuplicationCorpusSample,
} from '../src/api/duplicationCorpus';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/duplicationCorpus', async () => {
  const actual = await vi.importActual<typeof import('../src/api/duplicationCorpus')>('../src/api/duplicationCorpus');
  return {
    ...actual,
    fetchDuplicationCorpusSamples: vi.fn(),
    createDuplicationCorpusSample: vi.fn(),
    deleteDuplicationCorpusSample: vi.fn(),
  };
});

const reqId = 'FEAT-DUPLICATION-CORPUS';
void reqId;

const schoolAdmin: AuthenticatedUser = {
  id: 'school_admin01',
  username: 'school_admin01',
  role: 'SCHOOL_ADMIN',
  collegeId: null,
  supervisorId: null,
  scope: 'SCHOOL',
};

const student: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

function renderCorpusRoute() {
  return render(
    <MemoryRouter initialEntries={['/duplication-corpus']}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

function sample(overrides: Partial<DuplicationCorpusSample> = {}): DuplicationCorpusSample {
  return {
    id: 'sample-001',
    title: '既有论文样本',
    subject: '计算机科学',
    year: 2024,
    content: '既有样本文本',
    source_type: 'paste',
    source_filename: null,
    created_by: 'school_admin01',
    created_at: '2024-01-01T00:00:00.000Z',
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

describe('FEAT-DUPLICATION-CORPUS frontend corpus page and API client contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchDuplicationCorpusSamples).mockReset();
    vi.mocked(createDuplicationCorpusSample).mockReset();
    vi.mocked(deleteDuplicationCorpusSample).mockReset();
  });

  it('FEAT-DUPLICATION-CORPUS:UI:AUTHZ:001 renders shared-session anonymous and denied-role states without corpus controls', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValueOnce({ response: { status: 401 } });
    const anonymousRender = renderCorpusRoute();
    expect(await screen.findByText(/请先登录学校管理人员账号后管理比对样本/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
    expect(screen.queryByRole('button', { name: '保存样本' })).not.toBeInTheDocument();
    anonymousRender.unmount();

    vi.mocked(fetchCurrentSession).mockResolvedValueOnce({ user: student });
    renderCorpusRoute();
    expect(await screen.findByRole('heading', { name: '无权访问本地比对样本库' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '保存样本' })).not.toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-CORPUS:UI:LOAD:001 loads SCHOOL_ADMIN samples from the API and shows empty state without fallback rows', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(fetchDuplicationCorpusSamples).mockResolvedValueOnce([]);
    const emptyRender = renderCorpusRoute();

    expect(await screen.findByText('暂无样本')).toBeInTheDocument();
    expect(screen.getByText(/新增样本后将出现在这里/)).toBeInTheDocument();
    expect(screen.queryByText('硬编码样本')).not.toBeInTheDocument();
    expect(fetchDuplicationCorpusSamples).toHaveBeenCalledTimes(1);
    emptyRender.unmount();

    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(fetchDuplicationCorpusSamples).mockResolvedValueOnce([
      sample({ id: 'sample-api-001', title: 'API 返回样本', subject: '法学', year: 2022 }),
    ]);
    renderCorpusRoute();

    expect(await screen.findByRole('heading', { name: 'API 返回样本' })).toBeInTheDocument();
    expect(screen.getByText(/法学 · 2022 · 粘贴文本/)).toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-CORPUS:UI:FILE:001 reads accepted UTF-8 .txt/.md files and rejects unsupported or over-5MB files before API calls', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(fetchDuplicationCorpusSamples).mockResolvedValue([]);
    const user = userEvent.setup();
    const { container } = renderCorpusRoute();

    await screen.findByRole('heading', { name: '本地比对样本库' });
    await user.upload(fileInput(container), new File(['Markdown 样本文本'], 'sample.md', { type: 'text/markdown' }));
    await waitFor(() => expect(screen.getByLabelText('样本文本')).toHaveValue('Markdown 样本文本'));
    expect(screen.getByText('已选择：sample.md')).toBeInTheDocument();

    fireEvent.change(fileInput(container), {
      target: {
        files: testFileList(
          new File(['DOCX'], 'sample.docx', {
            type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
          }),
        ),
      },
    });
    expect(await screen.findByText('仅支持上传 .txt、.md 或 .pdf 文件')).toBeInTheDocument();
    expect(createDuplicationCorpusSample).not.toHaveBeenCalled();

    const oversizedFile = new File(['x'.repeat(5 * 1024 * 1024 + 1)], 'oversized.txt', { type: 'text/plain' });
    await user.upload(fileInput(container), oversizedFile);
    expect(screen.getByText('文件大小不能超过 5 MB')).toBeInTheDocument();
    expect(createDuplicationCorpusSample).not.toHaveBeenCalled();
  });

  it('FEAT-DUPLICATION-CORPUS:SCENARIO:001 submits title, subject, year, UTF-8 content, and displays the persisted sample', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(fetchDuplicationCorpusSamples).mockResolvedValue([]);
    vi.mocked(createDuplicationCorpusSample).mockResolvedValue(
      sample({
        id: 'created-sample-001',
        title: '人工智能课程论文样本',
        subject: '计算机科学',
        year: 2024,
        content: '这是一份非空 UTF-8 样本文本。',
      }),
    );
    const user = userEvent.setup();

    renderCorpusRoute();

    await user.type(await screen.findByLabelText('标题'), '人工智能课程论文样本');
    await user.type(screen.getByLabelText('学科'), '计算机科学');
    await user.clear(screen.getByLabelText('年份'));
    await user.type(screen.getByLabelText('年份'), '2024');
    await user.type(screen.getByLabelText('样本文本'), '这是一份非空 UTF-8 样本文本。');
    await user.click(screen.getByRole('button', { name: '保存样本' }));

    await waitFor(() =>
      expect(createDuplicationCorpusSample).toHaveBeenCalledWith({
        title: '人工智能课程论文样本',
        subject: '计算机科学',
        year: 2024,
        content: '这是一份非空 UTF-8 样本文本。',
        source_type: 'paste',
        source_filename: null,
      }),
    );
    expect(await screen.findByRole('heading', { name: '人工智能课程论文样本' })).toBeInTheDocument();
    expect(screen.getByText(/不表示已接入真实校内论文库/)).toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-CORPUS:UI:DELETE:001 removes a sample from the list only after delete API success', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(fetchDuplicationCorpusSamples).mockResolvedValue([
      sample({ id: 'delete-ok', title: '可删除样本' }),
      sample({ id: 'delete-fails', title: '保留样本' }),
    ]);
    vi.mocked(deleteDuplicationCorpusSample).mockResolvedValueOnce();
    const user = userEvent.setup();

    renderCorpusRoute();

    const article = (await screen.findByRole('heading', { name: '可删除样本' })).closest('article');
    expect(article).not.toBeNull();
    await user.click(within(article as HTMLElement).getByRole('button', { name: '删除样本' }));

    await waitFor(() => expect(deleteDuplicationCorpusSample).toHaveBeenCalledWith('delete-ok'));
    expect(screen.queryByRole('heading', { name: '可删除样本' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '保留样本' })).toBeInTheDocument();
  });

  it('FEAT-DUPLICATION-CORPUS:API-CLIENT:001 uses the shared same-origin Axios client for list, create, and delete calls', async () => {
    const getSpy = vi.spyOn(apiClient, 'get').mockResolvedValueOnce({ data: { samples: [sample()] } });
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({ data: sample({ id: 'client-created' }) });
    const deleteSpy = vi.spyOn(apiClient, 'delete').mockResolvedValueOnce({});
    const realApi =
      await vi.importActual<typeof import('../src/api/duplicationCorpus')>('../src/api/duplicationCorpus');
    const payload = {
      title: '客户端样本',
      subject: '管理学',
      year: 2024,
      content: '客户端提交样本文本',
      source_type: 'file' as const,
      source_filename: 'client.txt',
    };

    await expect(realApi.fetchDuplicationCorpusSamples()).resolves.toHaveLength(1);
    await expect(realApi.createDuplicationCorpusSample(payload)).resolves.toMatchObject({ id: 'client-created' });
    await expect(realApi.deleteDuplicationCorpusSample('client-created')).resolves.toBeUndefined();

    expect(getSpy).toHaveBeenCalledWith('/normative/duplication-corpus');
    expect(postSpy).toHaveBeenCalledWith('/normative/duplication-corpus', payload);
    expect(deleteSpy).toHaveBeenCalledWith('/normative/duplication-corpus/client-created');
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
    getSpy.mockRestore();
    postSpy.mockRestore();
    deleteSpy.mockRestore();
  });
});
