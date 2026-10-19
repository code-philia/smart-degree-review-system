import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import RuleConfigPage from '../src/pages/RuleConfigPage';
import apiClient from '../src/api';
import { useAuthSession } from '../src/auth/AuthSessionProvider';
vi.mock('../src/api', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
vi.mock('../src/auth/AuthSessionProvider', () => ({ useAuthSession: vi.fn() }));
vi.mock('../src/api/ruleConfig', () => ({ fetchRuleConfigurations: vi.fn(async () => ({ rules: [] })), publishRuleConfiguration: vi.fn(), resetCollegeRuleConfiguration: vi.fn() }));
vi.mock('../src/components/RuleDraftImportPanel', () => ({ default: () => null }));
beforeEach(() => {vi.mocked(apiClient.get).mockReset();vi.mocked(apiClient.put).mockReset();});
describe('fixed detector configuration', () => {
  it.each(['SCHOOL_ADMIN','COLLEGE_ADMIN'])('has no automatic repair controls or control API calls for %s',async role=>{
    vi.mocked(useAuthSession).mockReturnValue({status:'authenticated',user:{id:'admin',username:'admin',role,scope:'SCHOOL'}} as ReturnType<typeof useAuthSession>);
    render(<MemoryRouter><RuleConfigPage /></MemoryRouter>);
    expect(await screen.findByText('暂无运行时规则配置')).toBeTruthy();
    expect(screen.queryByRole('switch')).toBeNull();expect(screen.queryByText(/自动迭代|冻结自动|恢复自动/)).toBeNull();
    expect(apiClient.get).not.toHaveBeenCalled();expect(apiClient.put).not.toHaveBeenCalled();
  });
  it('retains the ordinary-user access boundary without control requests',async()=>{
    vi.mocked(useAuthSession).mockReturnValue({status:'authenticated',user:{id:'student',username:'student',role:'STUDENT',scope:'SCHOOL'}} as ReturnType<typeof useAuthSession>);
    render(<MemoryRouter><RuleConfigPage /></MemoryRouter>);
    expect(await screen.findByText('无权维护规则配置')).toBeTruthy();expect(apiClient.get).not.toHaveBeenCalled();
  });
});
