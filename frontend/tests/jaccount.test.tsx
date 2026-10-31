import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import AuthPage from '../src/pages/AuthPage';

afterEach(() => window.history.replaceState({}, '', '/'));

describe('campus sign-in entry', () => {
  it('links to server-side campus authorization while retaining password sign-in', () => {
    render(<AuthPage />);
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
    expect(screen.getByRole('heading', { name: '登录本地账号' })).toBeInTheDocument();
    expect(screen.queryByText(/试点版本暂未开放/)).not.toBeInTheDocument();
  });

  it.each(['state', 'provider', 'denied', 'unavailable'])('offers a new login attempt after a %s callback error', (error) => {
    window.history.replaceState({}, '', '/auth?jaccount_error=' + error);
    render(<AuthPage />);
    expect(screen.getByRole('alert')).toHaveTextContent(/jAccount/);
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
  });

  it.each(['unexpected', '__proto__', 'constructor'])('keeps sign-in usable for an unrecognized callback error %s', (error) => {
    window.history.replaceState({}, '', '/auth?jaccount_error=' + error);
    render(<AuthPage />);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
  });
});
