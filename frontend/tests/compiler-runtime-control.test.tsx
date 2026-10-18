import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RuleConfigPage from '../src/pages/RuleConfigPage';
import apiClient from '../src/api';
import { useAuthSession } from '../src/auth/AuthSessionProvider';
vi.mock('../src/api', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
vi.mock('../src/auth/AuthSessionProvider', () => ({ useAuthSession: vi.fn() }));
vi.mock('../src/api/ruleConfig', () => ({ fetchRuleConfigurations: vi.fn(async () => ({ rules: [] })), publishRuleConfiguration: vi.fn(), resetCollegeRuleConfiguration: vi.fn() }));
vi.mock('../src/components/RuleDraftImportPanel', () => ({ default: () => null }));
const state = (freeze = false) => ({ freeze, generation: 1, active_version: null, active_path: null });
function show(role = 'SCHOOL_ADMIN') {
  vi.mocked(useAuthSession).mockReturnValue({ status: 'authenticated', user: { id: 'admin', username: 'admin', role, scope: 'SCHOOL' } } as ReturnType<typeof useAuthSession>);
  render(<MemoryRouter><RuleConfigPage /></MemoryRouter>);
}
beforeEach(() => { vi.mocked(apiClient.get).mockReset().mockResolvedValue({ data: state() }); vi.mocked(apiClient.put).mockReset().mockResolvedValue({ data: state(true) }); });
describe('administrator freeze switch', () => {
  it('explains that management is unavailable without crashing the configuration page', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce({ isAxiosError: true, response: { status: 503 } }); show();
    expect(await screen.findByText('自动迭代管理暂未启用，请联系管理员。')).toBeTruthy();
    expect(screen.getByRole('heading', { name: '基础规则检测规则配置' })).toBeTruthy();
    expect(screen.queryByRole('switch')).toBeNull();
  });

  it('shows default iteration and stores checked=true as freeze=true', async () => {
    show(); const user = userEvent.setup();
    expect(await screen.findByText('自动迭代：开启（默认）')).toBeTruthy();
    const toggle = screen.getByRole('switch', { name: '冻结自动迭代' }); expect(toggle).not.toBeChecked();
    await user.click(toggle);
    expect(await screen.findByText('自动迭代：冻结')).toBeTruthy(); expect(toggle).toBeChecked();
    expect(apiClient.put).toHaveBeenCalledWith('/normative/paper-lint/control/freeze', { freeze: true }, { timeout: 60_000 });
    vi.mocked(apiClient.put).mockResolvedValueOnce({ data: state(false) }); await user.click(toggle);
    expect(await screen.findByText('自动迭代：开启（默认）')).toBeTruthy();
    expect(apiClient.put).toHaveBeenLastCalledWith('/normative/paper-lint/control/freeze', { freeze: false }, { timeout: 60_000 });
  });
  it('loads an existing frozen setting without changing it', async () => {
    vi.mocked(apiClient.get).mockResolvedValueOnce({ data: state(true) }); show('COLLEGE_ADMIN');
    expect(await screen.findByRole('switch', { name: '冻结自动迭代' })).toBeChecked(); expect(apiClient.put).not.toHaveBeenCalled();
  });
  it('keeps the prior state and shows a useful error when saving fails', async () => {
    vi.mocked(apiClient.put).mockRejectedValueOnce(new Error('private backend detail')); show();
    const toggle = await screen.findByRole('switch', { name: '冻结自动迭代' }); await userEvent.click(toggle);
    expect(await screen.findByText('自动迭代设置未保存，请重试。')).toBeTruthy(); expect(toggle).not.toBeChecked();
    expect(screen.queryByText('private backend detail')).toBeNull();
  });
  it('does not show or request global controls for ordinary users', async () => {
    show('STUDENT'); await screen.findByText('无权维护规则配置');
    expect(screen.queryByRole('switch')).toBeNull(); expect(apiClient.get).not.toHaveBeenCalled();
  });
  it('does not pretend iteration is enabled when status cannot be loaded', async () => {
    vi.mocked(apiClient.get).mockRejectedValueOnce(new Error('unavailable')); show();
    expect(await screen.findByText('自动迭代状态暂不可用，请重试。')).toBeTruthy(); expect(screen.queryByRole('switch')).toBeNull();
    expect(screen.queryByText('自动迭代：开启（默认）')).toBeNull();
  });
});
