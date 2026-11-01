import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AuthPage from '../src/pages/AuthPage';
import { AuthSessionProvider, useAuthSession } from '../src/auth/AuthSessionProvider';
import * as api from '../src/api/authSession';

vi.mock('../src/api/authSession',async () => ({
  ...await vi.importActual('../src/api/authSession'),
  fetchCurrentSession:vi.fn(),loginWithTrialAccount:vi.fn(),
}));
function Home() { const {user}=useAuthSession();return <p>{user?.username}:{user?.role}</p>; }
function show() {
  render(<MemoryRouter initialEntries={['/auth']}><AuthSessionProvider><Routes>
    <Route path="/auth" element={<AuthPage/>}/><Route path="/paper-upload" element={<Home/>}/>
  </Routes></AuthSessionProvider></MemoryRouter>);
}
describe('hidden trial login dialog',() => {
  beforeEach(() => {
    vi.mocked(api.fetchCurrentSession).mockRejectedValue(new Error('anonymous'));
    vi.mocked(api.loginWithTrialAccount).mockReset();
  });
  it('keeps the form hidden until the existing version text is clicked and focuses the account field',async () => {
    show();const user=userEvent.setup();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('账号')).not.toBeInTheDocument();
    expect(screen.getByRole('link',{name:/使用 jAccount 登录/})).toBeInTheDocument();
    await user.click(screen.getByRole('button',{name:'试点验证版 V0.9'}));
    expect(screen.getByRole('dialog',{name:'试验账号登录'})).toBeInTheDocument();
    expect(screen.getByLabelText('密码')).toHaveAttribute('type','password');
    await waitFor(()=>expect(screen.getByLabelText('账号')).toHaveFocus());
  });
  it.each([['student01','STUDENT'],['supervisor01','SUPERVISOR'],['college_admin01','COLLEGE_ADMIN'],['school_admin01','SCHOOL_ADMIN']])(
    'signs %s in through the trial endpoint and keeps its server-assigned role',async (username,role) => {
      vi.mocked(api.loginWithTrialAccount).mockResolvedValue({user:{id:username,username,role:role as api.AuthRole,collegeId:null,supervisorId:null,scope:'SCHOOL'}});
      show();const user=userEvent.setup();
      await user.click(screen.getByRole('button',{name:'试点验证版 V0.9'}));
      await user.type(screen.getByLabelText('账号'),username);
      await user.type(screen.getByLabelText('密码'),'test-password');
      await user.click(screen.getByRole('button',{name:'登录'}));
      expect(await screen.findByText(username+':'+role)).toBeInTheDocument();
      expect(api.loginWithTrialAccount).toHaveBeenCalledWith({username,password:'test-password'});
    });
  it('shows a failed login without authenticating and clears the password',async () => {
    vi.mocked(api.loginWithTrialAccount).mockRejectedValue(new Error('账号或密码错误，请重试。'));
    show();const user=userEvent.setup();
    await user.click(screen.getByRole('button',{name:'试点验证版 V0.9'}));
    await user.type(screen.getByLabelText('账号'),'student01');await user.type(screen.getByLabelText('密码'),'wrong');
    await user.click(screen.getByRole('button',{name:'登录'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('账号或密码错误');
    expect(screen.getByLabelText('密码')).toHaveValue('');
    await waitFor(()=>expect(screen.getByLabelText('密码')).toHaveFocus());
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
  it('clears credentials on Escape and returns focus to the version label',async () => {
    show();const user=userEvent.setup();const trigger=screen.getByRole('button',{name:'试点验证版 V0.9'});
    await user.click(trigger);await user.type(screen.getByLabelText('账号'),'student01');
    await user.type(screen.getByLabelText('密码'),'temporary-secret');await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();await user.click(trigger);
    expect(screen.getByLabelText('账号')).toHaveValue('');expect(screen.getByLabelText('密码')).toHaveValue('');
  });
  it('prevents duplicate submits while login is pending',async () => {
    let reject!:(error:Error)=>void;
    vi.mocked(api.loginWithTrialAccount).mockReturnValue(new Promise((_,r)=>{reject=r;}));
    show();const user=userEvent.setup();await user.click(screen.getByRole('button',{name:'试点验证版 V0.9'}));
    await user.type(screen.getByLabelText('账号'),'student01');await user.type(screen.getByLabelText('密码'),'password');
    const form=screen.getByRole('form',{name:'试验账号登录表单'});
    fireEvent.submit(form);fireEvent.submit(form);
    expect(api.loginWithTrialAccount).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button',{name:'登录中…'})).toBeDisabled();
    await act(async()=>{reject(new Error('稍后重试'));});
    expect(screen.getByRole('alert')).toHaveTextContent('稍后重试');
  });
});
