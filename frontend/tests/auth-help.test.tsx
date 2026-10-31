import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';

describe('FEAT-AUTH-HELP local login help', () => {
  it('renders the /auth page shell without exposing local account credentials', async () => {
    render(
      <MemoryRouter initialEntries={['/auth']}>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '统一身份认证' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '登录本地账号' })).toBeInTheDocument();
    expect(screen.getByLabelText('本地账号登录帮助')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
    expect(screen.queryByText('ArcDemo123!')).not.toBeInTheDocument();
    expect(screen.queryByText('student01')).not.toBeInTheDocument();
    expect(screen.queryByText('supervisor01')).not.toBeInTheDocument();
    expect(screen.queryByText('college_admin01')).not.toBeInTheDocument();
    expect(screen.queryByText('school_admin01')).not.toBeInTheDocument();
  });

  it('explains how to request a local account without disclosing credentials', async () => {
    render(
      <MemoryRouter initialEntries={['/auth']}>
        <AuthSessionProvider>
          <App />
        </AuthSessionProvider>
      </MemoryRouter>,
    );

    await userEvent.click(screen.getByText('本地账号登录帮助'));
    expect(screen.getByText(/请向管理员申请/)).toBeInTheDocument();
    expect(screen.getByText(/本地账号登录继续保留/)).toBeInTheDocument();
  });
});
