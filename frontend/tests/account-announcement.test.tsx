import { StrictMode } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(()=>({post:vi.fn(),get:vi.fn(),user:{id:'account-a',username:'account-a',role:'STUDENT',scope:'SCHOOL',collegeId:null,supervisorId:null}}));
vi.mock('../src/api',()=>({default:{post:mocks.post,get:mocks.get}}));
vi.mock('../src/auth/AuthSessionProvider',()=>({useAuthSession:()=>({status:'authenticated',user:mocks.user,logout:vi.fn()})}));
import AppShell from '../src/layout/AppShell';
import { setLocale } from '../src/i18n/locale';

function Content(){const location=useLocation();return <><h1>已登录主页</h1><output>{location.pathname}</output></>;}
function Shell({path='/paper-upload'}:{path?:string}){return <MemoryRouter initialEntries={[path]}><Routes><Route element={<AppShell/>}><Route path="*" element={<Content/>}/></Route></Routes></MemoryRouter>;}
beforeEach(()=>{
  setLocale('zh');mocks.user.id='account-a';mocks.user.username='account-a';
  mocks.get.mockReset().mockResolvedValue({data:{items:[],unreadCount:0,total:0}});
  mocks.post.mockReset().mockResolvedValue({data:{announcement_id:'feedback-2026-11-24',show:true}});
});
afterEach(()=>{act(()=>setLocale('zh'));});

describe('real authenticated shell announcement',()=>{
  it('shows a first account grant with approved copy and returns focus to the real feedback entry',async()=>{
    const user=userEvent.setup();render(<Shell/>);
    const dialog=await screen.findByRole('dialog',{name:'欢迎反馈'});
    expect(dialog).toHaveTextContent('Use Feedback at the top right to share issues or suggestions.');
    const link=screen.getByRole('link',{name:/吐槽微信群\s*WeChat feedback group/});
    expect(link).toHaveAttribute('href','https://feedback-chat-5d9.pages.dev/');
    expect(link).toHaveAttribute('target','_blank');expect(link).toHaveAttribute('rel','noopener noreferrer');
    expect(dialog).not.toHaveTextContent('Share feedback');expect(dialog).not.toHaveTextContent('Get started');
    expect(dialog).not.toHaveTextContent('仅展示一次');expect(dialog).not.toHaveTextContent('直接交流');
    await user.click(screen.getByRole('button',{name:'开始使用',exact:true}));
    await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(()=>expect(screen.getByRole('button',{name:'使用反馈',exact:true})).toHaveFocus());
    await user.click(screen.getByRole('button',{name:'使用反馈',exact:true}));
    expect(screen.getByRole('dialog',{name:'使用反馈'})).toBeInTheDocument();
  });
  it('does not show the notice for an already recorded account',async()=>{
    mocks.post.mockResolvedValue({data:{announcement_id:'feedback-2026-11-24',show:false}});
    render(<Shell/>);await waitFor(()=>expect(mocks.post).toHaveBeenCalled());
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'已登录主页'})).toBeInTheDocument();
  });
  it('does not lose the first grant or issue duplicate requests in React StrictMode',async()=>{
    render(<StrictMode><Shell/></StrictMode>);
    expect(await screen.findByRole('dialog',{name:'欢迎反馈'})).toBeInTheDocument();
    expect(mocks.post).toHaveBeenCalledTimes(1);
  });
  it('retries a failed response using the same idempotency token',async()=>{
    mocks.post.mockRejectedValueOnce(new Error('response lost'));
    render(<Shell/>);expect(await screen.findByRole('dialog',{name:'欢迎反馈'})).toBeInTheDocument();
    expect(mocks.post).toHaveBeenCalledTimes(2);
    expect(mocks.post.mock.calls[0][1].request_id).toBe(mocks.post.mock.calls[1][1].request_id);
    expect(mocks.post.mock.calls[0][1].expected_user_id).toBe('account-a');
    expect(mocks.post.mock.calls[1][1].expected_user_id).toBe('account-a');
  });
  it('keeps the authenticated page usable when both attempts fail',async()=>{
    mocks.post.mockRejectedValue(new Error('temporarily unavailable'));
    render(<Shell/>);await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByRole('heading',{name:'已登录主页'})).toBeInTheDocument();
  });
  it('ignores an old account response after the account changes',async()=>{
    let finish!:(value:unknown)=>void;
    mocks.post.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValue({data:{show:false}});
    const view=render(<Shell/>);await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(1));
    mocks.user.id='account-b';mocks.user.username='account-b';view.rerender(<Shell/>);
    await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(2));
    expect(mocks.post.mock.calls[0][1].expected_user_id).toBe('account-a');
    expect(mocks.post.mock.calls[1][1].expected_user_id).toBe('account-b');
    await act(async()=>finish({data:{show:true}}));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
  it('consults the server again on another login instead of reusing a browser display flag',async()=>{
    mocks.post.mockResolvedValueOnce({data:{show:true}}).mockResolvedValue({data:{show:false}});
    const first=render(<Shell/>);await screen.findByRole('dialog',{name:'欢迎反馈'});first.unmount();
    render(<Shell/>);await waitFor(()=>expect(mocks.post).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(mocks.post.mock.calls[0][1].request_id).not.toBe(mocks.post.mock.calls[1][1].request_id);
  });
  it('preserves bilingual notice content and a report deep link for an English jAccount session',async()=>{
    mocks.user.id='jaccount:person-a';act(()=>setLocale('en'));
    const user=userEvent.setup();render(<Shell path="/reports/pdf/example"/>);
    const dialog=await screen.findByRole('dialog',{name:'欢迎反馈'});
    expect(dialog).toHaveTextContent('吐槽微信群');expect(dialog).toHaveTextContent('WeChat feedback group');
    await user.keyboard('{Escape}');
    await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText('/reports/pdf/example')).toBeInTheDocument();
    await waitFor(()=>expect(screen.getByRole('button',{name:'Feedback',exact:true})).toHaveFocus());
  });
});
