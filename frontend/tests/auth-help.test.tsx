import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';

describe('public campus-only sign-in page', () => {
  it('renders the /auth page shell without exposing local account credentials', async () => {
    render(
      <MemoryRouter initialEntries={['/auth']}>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '智慧学位AI评阅辅助系统', level: 2 })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: '登录本地账号' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('本地账号登录帮助')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
    expect(screen.queryByText('ArcDemo123!')).not.toBeInTheDocument();
    expect(screen.queryByText('student01')).not.toBeInTheDocument();
    expect(screen.queryByText('supervisor01')).not.toBeInTheDocument();
    expect(screen.queryByText('college_admin01')).not.toBeInTheDocument();
    expect(screen.queryByText('school_admin01')).not.toBeInTheDocument();
  });

  it('keeps the system description without local account recovery actions', async () => {
    render(
      <MemoryRouter initialEntries={['/auth']}>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    expect(screen.getByLabelText('系统说明')).toBeInTheDocument();
    expect(screen.queryByText(/忘记密码|本地账号登录帮助|本地账号登录继续保留/)).not.toBeInTheDocument();
  });
});
