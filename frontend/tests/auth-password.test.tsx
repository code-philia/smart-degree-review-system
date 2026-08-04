import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import LocalAccountLoginForm from '../src/auth/LocalAccountLoginForm';
import RoleAwareHomeMenu from '../src/auth/RoleAwareHomeMenu';
import {
  fetchCurrentSession,
  loginWithLocalAccount,
  type AuthenticatedUser,
} from '../src/api/authSession';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
    loginWithLocalAccount: vi.fn(),
  };
});

const reqId = 'FEAT-AUTH-PASSWORD';
void reqId;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

const schoolAdminUser: AuthenticatedUser = {
  id: 'school_admin01',
  username: 'school_admin01',
  role: 'SCHOOL_ADMIN',
  collegeId: null,
  supervisorId: null,
  scope: 'SCHOOL',
};

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('FEAT-AUTH-PASSWORD frontend local login and role-aware home menu', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(loginWithLocalAccount).mockReset();
  });

  it('renders loading then login-required home menu before the session is recovered', async () => {
    const pending = deferred<{ user: AuthenticatedUser }>();
    vi.mocked(fetchCurrentSession).mockReturnValue(pending.promise);

    render(
      <AuthSessionProvider>
        <RoleAwareHomeMenu />
      </AuthSessionProvider>,
    );

    expect(screen.getByText('正在加载登录状态…')).toBeInTheDocument();

    pending.reject({ response: { status: 401 } });
    await waitFor(() => expect(screen.getByText('请登录后查看角色菜单和数据范围。')).toBeInTheDocument());
  });

  it('shows the student menu and scope from the shared session user rather than local fallback data', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });

    render(
      <AuthSessionProvider>
        <RoleAwareHomeMenu />
      </AuthSessionProvider>,
    );

    expect(await screen.findByRole('region', { name: '当前角色菜单' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '学生菜单' })).toBeInTheDocument();
    expect(screen.getByText('数据范围：本学院')).toBeInTheDocument();
    expect(screen.queryByText('学校管理菜单')).not.toBeInTheDocument();
  });

  it('routes invalid local credentials to the unified user-facing error and no authenticated feedback', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });
    vi.mocked(loginWithLocalAccount).mockRejectedValue({ response: { status: 401 } });
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AuthSessionProvider>
          <LocalAccountLoginForm />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    await user.type(await screen.findByLabelText('账号'), 'student01');
    await user.type(screen.getByLabelText('密码'), 'WrongPassword123!');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByText('用户名或密码错误')).toBeInTheDocument();
    expect(screen.queryByText(/已登录：student01（STUDENT）/)).not.toBeInTheDocument();
    expect(screen.queryByText('账号是否存在')).not.toBeInTheDocument();
  });

  it('keeps the authenticated role menu synced to the provider user and displays school scope correctly', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: schoolAdminUser });

    render(
      <AuthSessionProvider>
        <RoleAwareHomeMenu />
      </AuthSessionProvider>,
    );

    expect(await screen.findByRole('region', { name: '当前角色菜单' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '学校管理菜单' })).toBeInTheDocument();
    expect(screen.getByText('数据范围：全校')).toBeInTheDocument();
  });
});
