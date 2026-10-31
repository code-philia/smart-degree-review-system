import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const authMocks = vi.hoisted(() => ({
  logout: vi.fn(async () => undefined),
  user: {
    id: 'student-ui-001', username: 'student01', role: 'STUDENT' as const,
    collegeId: 'college-001', supervisorId: 'supervisor-001', scope: 'COLLEGE' as const,
    displayName: undefined as string | undefined,
  },
}));

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({
    status: 'authenticated' as const,
    user: authMocks.user,
    logout: authMocks.logout,
  }),
}));

import AppShell from '../src/layout/AppShell';

function renderShell(path = '/thirty-rules-check') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/thirty-rules-check" element={<h1>PDF 检测内容</h1>} />
          <Route path="/thirty-rules-check/reports" element={<h1>历史报告内容</h1>} />
          <Route path="/thirty-rules-check/reports/pdf/:reportId" element={<h1>报告详情内容</h1>} />
        </Route>
        <Route path="/auth" element={<h1>登录页</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AppShell shadcn layout', () => {
  beforeEach(() => {
    authMocks.logout.mockClear();
    Object.assign(authMocks.user, { id: 'student-ui-001', username: 'student01', displayName: undefined });
  });

  it.each([
    ['/thirty-rules-check', '论文上传'],
    ['/thirty-rules-check/reports', '历史报告'],
    ['/thirty-rules-check/reports/pdf/example', '历史报告'],
  ])('marks exactly one sidebar destination on %s', (path, selectedLabel) => {
    const { container } = renderShell(path);
    const links = [...container.querySelectorAll('[aria-label="主导航菜单"] a')];
    const active = links.filter(link => link.getAttribute('data-active') === 'true');
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveTextContent(selectedLabel);
    expect(active[0]).toHaveAttribute('aria-current', 'page');
    expect(links.filter(link => link.getAttribute('aria-current') === 'page')).toEqual(active);
  });

  it('shows the campus name in the account button and menu without role or scope captions', async () => {
    Object.assign(authMocks.user, { id: 'jaccount:person-1', username: 'jaccount:campus-account', displayName: '张三' });
    const user = userEvent.setup();
    renderShell();
    const account = screen.getByRole('button', { name: /张三/ });
    expect(account).toHaveTextContent('张三');
    expect(account).not.toHaveTextContent('学生');
    expect(screen.queryByText('jaccount:campus-account')).not.toBeInTheDocument();
    await user.click(account);
    expect(screen.getByRole('menu')).toHaveTextContent('张三');
    expect(screen.getByRole('menu')).not.toHaveTextContent('学生');
    expect(screen.getByRole('menu')).not.toHaveTextContent('本人范围');
  });

  it('keeps role-aware navigation and supports the shadcn sidebar collapsed state', async () => {
    const user = userEvent.setup();
    const { container } = renderShell();

    expect(screen.getAllByRole('link', { name: '论文上传' })[0]).toHaveAttribute('href', '/thirty-rules-check');
    expect(screen.getAllByRole('link', { name: '历史报告' })[0]).toHaveAttribute('href', '/thirty-rules-check/reports');
    expect(screen.queryByRole('link', { name: '内置审查案例' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'PDF 检测内容' })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: '切换主导航' }));
    expect(container.querySelector('[data-slot="sidebar"]')).toHaveAttribute('data-state', 'collapsed');
  });

  it('logs out from the shadcn account dropdown and returns to the login route', async () => {
    const user = userEvent.setup();
    renderShell();

    await user.click(screen.getByRole('button', { name: /student01/ }));
    await user.click(screen.getByRole('menuitem', { name: '退出登录' }));

    expect(authMocks.logout).toHaveBeenCalledOnce();
    expect(await screen.findByRole('heading', { name: '登录页' })).toBeInTheDocument();
  });
});
