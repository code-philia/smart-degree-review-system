import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import App from '../src/App';
import DemoAccountHelpPanel from '../src/auth/DemoAccountHelpPanel';

const expectedAccounts = [
  ['student01', '学生'],
  ['supervisor01', '导师'],
  ['college_admin01', '学院管理人员'],
  ['school_admin01', '学校管理人员'],
] as const;

describe('FEAT-AUTH-HELP local login help', () => {
  it('renders the /auth page shell with the demo help disclosure and login form', () => {
    render(
      <MemoryRouter initialEntries={['/auth']}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: '统一身份认证' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '登录本地账号' })).toBeInTheDocument();
    expect(screen.getByText('短信验证码登录不属于本版本实现范围')).toBeInTheDocument();
    expect(screen.getByLabelText('演示账号与登录帮助')).toBeInTheDocument();
    expect(screen.getByText(/未接入 jAccount、短信验证码或扫码登录/)).toBeInTheDocument();
    expect(screen.getByText(/默认演示密码为\s*ArcDemo123!/)).toBeInTheDocument();

    const roster = screen.getByLabelText('四类演示账号');
    for (const [username, role] of expectedAccounts) {
      expect(within(roster).getByRole('heading', { name: username })).toBeInTheDocument();
      expect(within(roster).getByText(role)).toBeInTheDocument();
    }
  });

  it('keeps the demo account help panel self-contained with the local prototype boundary copy', () => {
    render(<DemoAccountHelpPanel />);

    expect(screen.getByLabelText('演示账号与登录帮助')).toBeInTheDocument();
    expect(
      screen.getByText(
        '试点版本目前仅支持账号密码方式登录。默认演示密码为 ArcDemo123!，四个账号分别对应不同角色，可用于体验登录后的界面与操作。',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText('说明：试点版本尚未接入 jAccount、短信验证码或扫码登录；如需登录，请直接使用上方试用账号与密码。'),
    ).toBeInTheDocument();
  });
});
