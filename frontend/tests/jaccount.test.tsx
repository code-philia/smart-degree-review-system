import { render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import AuthPage from '../src/pages/AuthPage';

afterEach(() => window.history.replaceState({}, '', '/'));

describe('campus sign-in entry', () => {
  it('preserves the requested report destination through campus sign-in',()=>{
    render(<AuthPage returnTo="/reports/pdf/123e4567-e89b-12d3-a456-426614174000"/>);
    expect(screen.getByRole('link',{name:'使用 jAccount 登录'})).toHaveAttribute('href','/api/auth/jaccount?return_to=%2Freports%2Fpdf%2F123e4567-e89b-12d3-a456-426614174000');
  });
  it('ignores an external return URL',()=>{
    render(<AuthPage returnTo="https://evil.example"/>);
    expect(screen.getByRole('link',{name:'使用 jAccount 登录'})).toHaveAttribute('href','/api/auth/jaccount');
  });
  it('keeps authentication and capabilities in the card with the full description above it', () => {
    render(<AuthPage />);
    const panel = screen.getByRole('region', { name: '身份认证区域' });
    expect(within(panel).getByRole('region', { name: '学位论文规范性检测' })).toBeInTheDocument();
    expect(screen.getByLabelText('系统说明')).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: '使用 jAccount 登录' })).toBeInTheDocument();
  });
  it('offers only server-side campus authorization without local password sign-in', () => {
    render(<AuthPage />);
    expect(screen.getByRole('link', { name: '使用 jAccount 登录' })).toHaveAttribute('href', '/api/auth/jaccount');
    expect(screen.queryByRole('heading', { name: '登录本地账号' })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(document.querySelector('input[type="password"]')).not.toBeInTheDocument();
    expect(screen.queryByText(/忘记密码|本地账号登录帮助/)).not.toBeInTheDocument();
    expect(screen.queryByText(/试点版本暂未开放/)).not.toBeInTheDocument();
  });

  it.each(['state', 'provider', 'denied', 'unavailable', 'forbidden_role'])('offers a new login attempt after a %s callback error', (error) => {
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
