import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, type AuthenticatedUser } from '../src/api/authSession';
import { fetchRuleConfigurations, importRuleDraftTemplate } from '../src/api/ruleConfig';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
  };
});

vi.mock('../src/api/ruleConfig', async () => {
  const actual = await vi.importActual<typeof import('../src/api/ruleConfig')>('../src/api/ruleConfig');
  return {
    ...actual,
    fetchRuleConfigurations: vi.fn(),
    importRuleDraftTemplate: vi.fn(),
  };
});

const reqId = 'FEAT-RULE-TEMPLATE-UPLOAD';
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

function renderRuleConfigRoute() {
  return render(
    <MemoryRouter initialEntries={['/rule-config']}>
      <AuthSessionProvider>
        <App />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

function jsonFile(name = 'rules.json', sizePadding = '') {
  return new File(
    [
      JSON.stringify([
        {
          rule_id: 'UPLOAD-001',
          title: '标题完整性',
          category: '结构规范',
          severity: '严重',
          enabled: true,
          message: '标题必须完整',
        },
      ]),
      sizePadding,
    ],
    name,
    { type: 'application/json' },
  );
}

function ruleDraftFileInput(container: HTMLElement) {
  const input = container.querySelector('input[name="ruleDraftTemplate"]');
  expect(input).toBeInstanceOf(HTMLInputElement);
  return input as HTMLInputElement;
}

describe('FEAT-RULE-TEMPLATE-UPLOAD frontend route and import panel contract', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(fetchRuleConfigurations).mockReset();
    vi.mocked(importRuleDraftTemplate).mockReset();
    vi.mocked(fetchRuleConfigurations).mockResolvedValue({ scope: { level: 'school' }, rules: [] });
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:UI:001 mounts the draft-only JSON upload panel only for authorized administrators', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });

    renderRuleConfigRoute();

    expect(await screen.findByRole('heading', { name: '基础规则检测规则配置' })).toBeInTheDocument();
    expect(screen.getByText(/JSON 规则集导入草稿/)).toBeInTheDocument();
    expect(screen.getByText(/仅保存为规则草稿，不会自动生效/)).toBeInTheDocument();
    expect(screen.getByText(/DOC\/DOCX 模板不支持自动推导规则/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '导入规则草稿' })).toBeInTheDocument();
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:UI:AUTHZ:001 keeps anonymous and denied-role users away from upload controls', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValueOnce({ response: { status: 401 } });
    const anonymousRender = renderRuleConfigRoute();
    expect(await screen.findByText(/请先登录学校或学院管理员账号后维护规则/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '导入规则草稿' })).not.toBeInTheDocument();
    anonymousRender.unmount();

    vi.mocked(fetchCurrentSession).mockResolvedValueOnce({ user: student });
    renderRuleConfigRoute();
    expect(await screen.findByRole('heading', { name: '无权维护规则配置' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '导入规则草稿' })).not.toBeInTheDocument();
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:UI:002 rejects missing and over-1MB files before calling the import API', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    const user = userEvent.setup();

    const { container } = renderRuleConfigRoute();

    await user.click(await screen.findByRole('button', { name: '导入规则草稿' }));
    expect(screen.getByText('请选择 UTF-8 JSON 规则集文件')).toBeInTheDocument();
    expect(importRuleDraftTemplate).not.toHaveBeenCalled();

    const oversizedFile = jsonFile('oversized-rules.json', 'x'.repeat(1024 * 1024 + 1));
    await user.upload(ruleDraftFileInput(container), oversizedFile);
    await user.click(screen.getByRole('button', { name: '导入规则草稿' }));

    expect(screen.getByText('文件大小不能超过 1 MB')).toBeInTheDocument();
    expect(importRuleDraftTemplate).not.toHaveBeenCalled();
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:SCENARIO:001 submits a valid JSON file and displays imported draft count without claiming active changes', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(importRuleDraftTemplate).mockResolvedValue({
      scope: { level: 'school' },
      imported_count: 2,
      draft_batch_id: 'batch-001',
      drafts: [
        { rule_id: 'UPLOAD-001', title: '标题完整性', category: '结构规范', severity: '严重', enabled: true },
        { rule_id: 'UPLOAD-002', title: '参考文献格式', category: '引用规范', severity: '一般', enabled: false },
      ],
    });
    const user = userEvent.setup();
    const file = jsonFile();

    const { container } = renderRuleConfigRoute();

    await screen.findByText(/JSON 规则集导入草稿/);
    await user.upload(ruleDraftFileInput(container), file);
    await user.click(screen.getByRole('button', { name: '导入规则草稿' }));

    await waitFor(() => expect(importRuleDraftTemplate).toHaveBeenCalledWith(file));
    expect(await screen.findByText('已创建 2 条规则草稿，未改变已生效规则。')).toBeInTheDocument();
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:SCENARIO:002 displays backend item-index validation text and does not show fake success', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdmin });
    vi.mocked(importRuleDraftTemplate).mockRejectedValue(
      new Error('第 0 项 rule_id 缺失；第 1 项 severity 必须为严重、一般、轻微'),
    );
    const user = userEvent.setup();

    const { container } = renderRuleConfigRoute();

    await screen.findByText(/JSON 规则集导入草稿/);
    await user.upload(ruleDraftFileInput(container), jsonFile('invalid-rules.json'));
    await user.click(screen.getByRole('button', { name: '导入规则草稿' }));

    expect(
      await screen.findByText('第 0 项 rule_id 缺失；第 1 项 severity 必须为严重、一般、轻微'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/已创建 .* 条规则草稿/)).not.toBeInTheDocument();
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:API-CLIENT:001 posts selected files as FormData through the shared Axios client', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValueOnce({
      data: { scope: { level: 'school' }, imported_count: 1, draft_batch_id: 'batch-client', drafts: [] },
    });
    const { importRuleDraftTemplate: realImportRuleDraftTemplate } =
      await vi.importActual<typeof import('../src/api/ruleConfig')>('../src/api/ruleConfig');
    const file = jsonFile('client-rules.json');

    await realImportRuleDraftTemplate(file);

    expect(postSpy).toHaveBeenCalledWith('/normative/rule-drafts/import', expect.any(FormData), expect.any(Object));
    const formData = postSpy.mock.calls[0][1] as FormData;
    expect(formData.get('file')).toBe(file);
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.interceptors.response).toBeDefined();
    postSpy.mockRestore();
  });
});
