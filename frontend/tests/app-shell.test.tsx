import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const authMocks = vi.hoisted(() => ({
  logout: vi.fn(async () => undefined),
}));

vi.mock('../src/auth/AuthSessionProvider', () => ({
  useAuthSession: () => ({
    status: 'authenticated' as const,
    user: {
      id: 'student-ui-001',
      username: 'student01',
      role: 'STUDENT' as const,
      collegeId: 'college-001',
      supervisorId: 'supervisor-001',
      scope: 'COLLEGE' as const,
    },
    logout: authMocks.logout,
  }),
}));

import AppShell from '../src/layout/AppShell';

function renderShell(path = '/about') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/about" element={<h1>系统说明内容</h1>} />
        </Route>
        <Route path="/auth" element={<h1>登录页</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('AppShell shadcn layout', () => {
  beforeEach(() => {
    authMocks.logout.mockClear();
  });

  it('keeps role-aware navigation and supports the shadcn sidebar collapsed state', async () => {
    const user = userEvent.setup();
    const { container } = renderShell();

    expect(screen.getByRole('link', { name: '提交报告给导师' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '内置审查案例' })).toHaveAttribute('href', '/review-cases');
    expect(screen.queryByRole('link', { name: '规则配置' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '系统说明内容' })).toBeInTheDocument();

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
