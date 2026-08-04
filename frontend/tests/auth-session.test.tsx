import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider, useAuthSession } from '../src/auth/AuthSessionProvider';
import LocalAccountLoginForm from '../src/auth/LocalAccountLoginForm';
import {
  fetchCurrentSession,
  loginWithLocalAccount,
  logoutCurrentSession,
  type AuthenticatedUser,
} from '../src/api/authSession';
import apiClient from '../src/api';

vi.mock('../src/api/authSession', async () => {
  const actual = await vi.importActual<typeof import('../src/api/authSession')>('../src/api/authSession');
  return {
    ...actual,
    fetchCurrentSession: vi.fn(),
    loginWithLocalAccount: vi.fn(),
    logoutCurrentSession: vi.fn(),
  };
});

const reqId = 'FEAT-AUTH-SESSION';
void reqId;

const studentUser: AuthenticatedUser = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE',
};

function SessionProbe() {
  const { status, user, logout } = useAuthSession();
  return (
    <section aria-label="全局会话状态">
      <p>status:{status}</p>
      <p>username:{user?.username ?? 'none'}</p>
      <p>role:{user?.role ?? 'none'}</p>
      <p>college:{user?.collegeId ?? 'none'}</p>
      <p>supervisor:{user?.supervisorId ?? 'none'}</p>
      <button type="button" onClick={() => void logout()}>
        退出登录
      </button>
    </section>
  );
}

describe('FEAT-AUTH-SESSION frontend session provider and auth page', () => {
  beforeEach(() => {
    vi.mocked(fetchCurrentSession).mockReset();
    vi.mocked(loginWithLocalAccount).mockReset();
    vi.mocked(logoutCurrentSession).mockReset();
  });

  it('recovers student01 relationship fields into the global provider state on mount', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });

    render(
      <AuthSessionProvider>
        <SessionProbe />
      </AuthSessionProvider>,
    );

    expect(screen.getByText('status:loading')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('status:authenticated')).toBeInTheDocument());
    expect(screen.getByText('username:student01')).toBeInTheDocument();
    expect(screen.getByText('role:STUDENT')).toBeInTheDocument();
    expect(screen.getByText('college:college01')).toBeInTheDocument();
    expect(screen.getByText('supervisor:supervisor01')).toBeInTheDocument();
  });

  it('enters anonymous state without a fake user when current session returns 401', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });

    render(
      <AuthSessionProvider>
        <SessionProbe />
      </AuthSessionProvider>,
    );

    await waitFor(() => expect(screen.getByText('status:anonymous')).toBeInTheDocument());
    expect(screen.getByText('username:none')).toBeInTheDocument();
    expect(screen.getByText('role:none')).toBeInTheDocument();
  });

  it('mounts the local login form through /auth and updates shared authenticated state on API-backed login', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });
    vi.mocked(loginWithLocalAccount).mockResolvedValue({ user: studentUser });
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={['/auth']}>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: '登录本地账号' })).toBeInTheDocument();
    expect(screen.getByRole('form', { name: '本地账号密码登录表单' })).toBeInTheDocument();

    await user.type(screen.getByLabelText('账号'), 'student01');
    await user.type(screen.getByLabelText('密码'), 'ArcDemo123!');
    await user.click(screen.getByRole('button', { name: '登录' }));

    await waitFor(() =>
      expect(loginWithLocalAccount).toHaveBeenCalledWith({ username: 'student01', password: 'ArcDemo123!' }),
    );
    expect(await screen.findByText(/已登录：student01（STUDENT）/)).toBeInTheDocument();
  });

  it('displays failed login errors without creating authenticated state', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });
    vi.mocked(loginWithLocalAccount).mockRejectedValue({ response: { status: 401 } });
    const user = userEvent.setup();

    render(
      <AuthSessionProvider>
        <LocalAccountLoginForm />
      </AuthSessionProvider>,
    );

    await user.type(await screen.findByLabelText('账号'), 'student01');
    await user.type(screen.getByLabelText('密码'), 'wrong-password');
    await user.click(screen.getByRole('button', { name: '登录' }));

    expect(await screen.findByText('账号或密码不正确，请重试。')).toBeInTheDocument();
    expect(screen.queryByText(/已登录：/)).not.toBeInTheDocument();
  });

  it('clears global user state on logout', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: studentUser });
    vi.mocked(logoutCurrentSession).mockResolvedValue();
    const user = userEvent.setup();

    render(
      <AuthSessionProvider>
        <SessionProbe />
      </AuthSessionProvider>,
    );

    await screen.findByText('username:student01');
    await user.click(screen.getByRole('button', { name: '退出登录' }));

    await waitFor(() => expect(screen.getByText('status:anonymous')).toBeInTheDocument());
    expect(screen.getByText('username:none')).toBeInTheDocument();
  });

  it('uses the shared interceptor-enabled Axios client for auth session calls', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
    expect(apiClient.defaults.baseURL).toBe('/api');
    expect(apiClient.interceptors.response).toBeDefined();
  });
});
