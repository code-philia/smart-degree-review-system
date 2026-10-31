import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession, loginWithLocalAccount } from '../src/api/authSession';

vi.mock('../src/api/authSession', async () => ({
  ...(await vi.importActual('../src/api/authSession')),
  fetchCurrentSession: vi.fn(),
  loginWithLocalAccount: vi.fn(),
}));
vi.mock('../src/pages/NormativeCheckPage', () => ({ default: () => <h1>Review workspace</h1> }));
vi.mock('../src/pages/NormativeReportPage', () => ({ default: () => <h1>Report history</h1> }));
vi.mock('../src/pages/PaperLintReportPage', () => ({ default: () => <h1>Saved PDF report</h1> }));

const student = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT' as const,
  collegeId: 'college01',
  supervisorId: 'supervisor01',
  scope: 'COLLEGE' as const,
};

function LocationProbe() {
  const location = useLocation();
  return (
    <output aria-label="Current route">
      {location.pathname}
      {location.search}
      {location.hash}
    </output>
  );
}

function mount(entry: string | { pathname: string; state: unknown }) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <AuthSessionProvider>
        <App />
        <LocationProbe />
      </AuthSessionProvider>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.mocked(fetchCurrentSession).mockReset();
  vi.mocked(loginWithLocalAccount).mockReset();
});

describe('workspace sign-in routing', () => {
  it.each(['/', '/thirty-rules-check', '/thirty-rules-check/reports/pdf/saved-report'])(
    'sends a guest at %s directly to sign-in',
    async (path) => {
      vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });
      mount(path);
      await waitFor(() => expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/auth$/));
      expect(screen.getByRole('form', { name: '本地账号密码登录表单' })).toBeInTheDocument();
      expect(screen.queryByLabelText('主导航')).not.toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: 'Saved PDF report' })).not.toBeInTheDocument();
    },
  );

  it('waits for session recovery before exposing the workspace or deciding to redirect', async () => {
    let resolve!: (value: { user: typeof student }) => void;
    vi.mocked(fetchCurrentSession).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    mount('/thirty-rules-check');
    expect(screen.queryByRole('heading', { name: 'Review workspace' })).not.toBeInTheDocument();
    expect(screen.getByLabelText('Current route')).toHaveTextContent('/thirty-rules-check');
    await act(async () => resolve({ user: student }));
    expect(await screen.findByRole('heading', { name: 'Review workspace' })).toBeInTheDocument();
  });

  it('keeps an authenticated report deep link available', async () => {
    vi.mocked(fetchCurrentSession).mockResolvedValue({ user: student });
    mount('/thirty-rules-check/reports/pdf/saved-report');
    expect(await screen.findByRole('heading', { name: 'Saved PDF report' })).toBeInTheDocument();
    expect(screen.getByLabelText('Current route')).toHaveTextContent('/thirty-rules-check/reports/pdf/saved-report');
  });

  it('returns a guest to the requested report after password sign-in', async () => {
    vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });
    vi.mocked(loginWithLocalAccount).mockResolvedValue({ user: student });
    const user = userEvent.setup();
    mount('/thirty-rules-check/reports/pdf/saved-report?view=pdf#page=3');
    await user.type(await screen.findByLabelText('账号'), 'student01');
    await user.type(screen.getByLabelText('密码'), 'test-password');
    await user.click(screen.getByRole('button', { name: '登录', exact: true }));
    expect(await screen.findByRole('heading', { name: 'Saved PDF report' })).toBeInTheDocument();
    expect(screen.getByLabelText('Current route')).toHaveTextContent(
      '/thirty-rules-check/reports/pdf/saved-report?view=pdf#page=3',
    );
  });

  it.each(['https://example.com/', '//example.com/', '/auth'])(
    'ignores an unsafe or looping post-login target %s',
    async (from) => {
      vi.mocked(fetchCurrentSession).mockRejectedValue({ response: { status: 401 } });
      vi.mocked(loginWithLocalAccount).mockResolvedValue({ user: student });
      const user = userEvent.setup();
      mount({ pathname: '/auth', state: { from } });
      await user.type(await screen.findByLabelText('账号'), 'student01');
      await user.type(screen.getByLabelText('密码'), 'test-password');
      await user.click(screen.getByRole('button', { name: '登录', exact: true }));
      expect(await screen.findByRole('heading', { name: 'Review workspace' })).toBeInTheDocument();
      expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/thirty-rules-check$/);
    },
  );
});
