import { act, render, screen } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import { fetchCurrentSession } from '../src/api/authSession';
import { setLocale } from '../src/i18n/locale';

vi.mock('../src/api/authSession', async () => ({
  ...(await vi.importActual('../src/api/authSession')), fetchCurrentSession: vi.fn(),
}));
vi.mock('../src/pages/NormativeCheckPage', () => ({ default: () => <h1>Review workspace</h1> }));
vi.mock('../src/pages/NormativeReportPage', () => ({ default: () => <h1>Report history</h1> }));
vi.mock('../src/pages/PaperLintReportPage', () => ({ default: () => <h1>Saved PDF report</h1> }));
vi.mock('../src/components/NotificationBell', () => ({ NotificationBell: () => null }));
const campusUser = { id:'jaccount:person-return', username:'jaccount:campus-user', role:'STUDENT' as const, scope:'COLLEGE' as const, collegeId:null, supervisorId:null };
function LocationProbe(){ const l=useLocation(); return <output aria-label="Current route">{l.pathname+l.search}</output>; }
function mount(entry:string){ return render(<MemoryRouter initialEntries={[entry]}><AuthSessionProvider><App/><LocationProbe/></AuthSessionProvider></MemoryRouter>); }
beforeEach(()=>{ vi.mocked(fetchCurrentSession).mockReset(); setLocale('zh'); window.history.replaceState({},'', '/'); });
describe('jAccount return routing',()=>{
  it.each(['/auth','/auth?jaccount_error=state'])('enters the homepage for a valid recovered session at %s',async(entry)=>{
    vi.mocked(fetchCurrentSession).mockResolvedValue({user:campusUser}); mount(entry);
    expect(await screen.findByRole('heading',{name:'Review workspace'})).toBeInTheDocument();
    expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/paper-upload$/);
    expect(screen.queryByRole('link',{name:'使用 jAccount 登录'})).not.toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('checks the existing session before showing an expired-login message',async()=>{
    let resolve!:(value:{user:typeof campusUser})=>void;
    vi.mocked(fetchCurrentSession).mockReturnValue(new Promise(done=>{resolve=done;}));
    window.history.replaceState({},'', '/auth?jaccount_error=state'); mount('/auth?jaccount_error=state');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('link',{name:'使用 jAccount 登录'})).not.toBeInTheDocument();
    await act(async()=>resolve({user:campusUser}));
    expect(await screen.findByRole('heading',{name:'Review workspace'})).toBeInTheDocument();
  });
  it('preserves the saved report and language after successful session recovery',async()=>{
    vi.mocked(fetchCurrentSession).mockResolvedValue({user:campusUser});
    const target='/reports/pdf/saved-report?lang=en'; mount('/auth?return_to='+encodeURIComponent(target));
    expect(await screen.findByRole('heading',{name:'Saved PDF report'})).toBeInTheDocument();
    expect(screen.getByLabelText('Current route')).toHaveTextContent(target);
  });
  it.each(['https://evil.example/','//evil.example/','/auth'])('ignores unsafe or looping return URLs %s',async(target)=>{
    vi.mocked(fetchCurrentSession).mockResolvedValue({user:campusUser}); mount('/auth?return_to='+encodeURIComponent(target));
    expect(await screen.findByRole('heading',{name:'Review workspace'})).toBeInTheDocument();
    expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/paper-upload$/);
  });
  it('keeps the genuine callback error visible when no valid session exists',async()=>{
    vi.mocked(fetchCurrentSession).mockRejectedValue({response:{status:401}});
    window.history.replaceState({},'', '/auth?jaccount_error=state'); mount('/auth?jaccount_error=state');
    expect(await screen.findByRole('alert')).toHaveTextContent('jAccount 登录已过期');
    expect(screen.getByLabelText('Current route')).toHaveTextContent(/^\/auth\?jaccount_error=state$/);
  });
});
