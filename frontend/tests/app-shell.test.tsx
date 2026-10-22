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

function renderShell(path = '/thirty-rules-check') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/thirty-rules-check" element={<h1>PDF 检测内容</h1>} />
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

    expect(screen.getAllByRole('link', { name: 'PDF 检测' })[0]).toHaveAttribute('href', '/thirty-rules-check');
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
