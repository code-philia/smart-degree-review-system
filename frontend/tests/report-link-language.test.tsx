import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import LocalAccountLoginForm from '../src/auth/LocalAccountLoginForm';
import * as api from '../src/api/authSession';
import { getLocale, setLocale } from '../src/i18n/locale';
vi.mock('../src/api/authSession',async()=>({...await vi.importActual('../src/api/authSession'),fetchCurrentSession:vi.fn(),loginWithTrialAccount:vi.fn(),loginWithLocalAccount:vi.fn()}));
vi.mock('../src/pages/PaperLintReportPage',()=>({default:()=> <p>Report loaded</p>}));
const user={id:'student01',username:'student01',role:'STUDENT',scope:'COLLEGE',collegeId:null,supervisorId:null} as api.AuthenticatedUser;
function LocationProbe(){const location=useLocation();return <output data-testid="location">{location.pathname+location.search}</output>;}
function NavigateProbe(){const navigate=useNavigate();return <button onClick={()=>navigate('/reports/pdf/report-1?lang=en')}>English report link</button>;}
function show(entry:string,local=false){
 return render(<MemoryRouter initialEntries={[entry]}><AuthSessionProvider>{local?<Routes><Route path="/auth" element={<LocalAccountLoginForm/>}/><Route path="/reports/pdf/:id" element={<p>Report loaded</p>}/></Routes>:<App/>}<LocationProbe/><NavigateProbe/></AuthSessionProvider></MemoryRouter>);
}
beforeEach(()=>{setLocale('zh');vi.mocked(api.fetchCurrentSession).mockRejectedValue(new Error('anonymous'));vi.mocked(api.loginWithTrialAccount).mockResolvedValue({user});vi.mocked(api.loginWithLocalAccount).mockResolvedValue({user});});
afterEach(()=>{cleanup();setLocale('zh');window.history.replaceState({},'','/');});
it.each(['zh','en'])('retains %s after an anonymous report link and refreshing its auth URL',async lang=>{
 setLocale(lang==='en'?'zh':'en');const report='/reports/pdf/report-1?lang='+lang;
 const view=show(report);
 const expected='/auth?lang='+lang+'&return_to=%2Freports%2Fpdf%2Freport-1%3Flang%3D'+lang;
 await waitFor(()=>expect(screen.getByTestId('location')).toHaveTextContent(expected));
 expect(getLocale()).toBe(lang);view.unmount();
 show(expected);expect(getLocale()).toBe(lang);
 expect(await screen.findByRole('link',{name:lang==='en'?'Sign in with jAccount':'使用 jAccount 登录'})).toHaveAttribute('href','/api/auth/jaccount?return_to=%2Freports%2Fpdf%2Freport-1%3Flang%3D'+lang);
});
it.each(['zh','en'])('returns a refreshed %s auth URL to its report after trial login',async lang=>{
 const report='/reports/pdf/report-1?lang='+lang;
 show('/auth?lang='+lang+'&return_to='+encodeURIComponent(report));const actor=userEvent.setup();
 await actor.click(screen.getByRole('button',{name:lang==='en'?'Shanghai Jiao Tong University emblem':'上海交通大学校徽'}));
 await actor.type(screen.getByLabelText(lang==='en'?'Account':'账号'),'student01');
 await actor.type(screen.getByLabelText(lang==='en'?'Password':'密码'),'test-password');
 await actor.click(screen.getByRole('button',{name:lang==='en'?'Sign in':'登录'}));
 await waitFor(()=>expect(screen.getByTestId('location')).toHaveTextContent(report));
 expect(getLocale()).toBe(lang);
});
it('returns local login to a validated report from a refreshed auth URL',async()=>{
 show('/auth?lang=en&return_to=%2Freports%2Fpdf%2Freport-1%3Flang%3Den',true);
 const actor=userEvent.setup();await actor.type(screen.getByLabelText('账号'),'student01');await actor.type(screen.getByLabelText('密码'),'test-password');await actor.click(screen.getByRole('button',{name:'登录'}));
 await waitFor(()=>expect(screen.getByTestId('location')).toHaveTextContent('/reports/pdf/report-1?lang=en'));
});
it('applies a different email language for an already signed-in navigation',async()=>{
 vi.mocked(api.fetchCurrentSession).mockResolvedValue({user});show('/reports/pdf/report-1?lang=zh');
 await screen.findByText('Report loaded');await userEvent.setup().click(screen.getByRole('button',{name:'English report link'}));
 await waitFor(()=>expect(getLocale()).toBe('en'));expect(document.documentElement.lang).toBe('en');
});
it.each(['https://evil.example','//evil.example','/reports/pdf/id?lang=en&next=https://evil.example','/reports/pdf/id?lang=en&lang=zh','/reports/pdf/id?lang=en\n','/reports/pdf/id\r','/reports/pdf/id?lang=zh\u2028','/reports/pdf/id\u2029'])('does not retain an unsafe report return query %s',async value=>{
 show('/auth?lang=zh&return_to='+encodeURIComponent(value));
 await act(async()=>{});
 expect(screen.getByRole('link',{name:'使用 jAccount 登录'})).toHaveAttribute('href','/api/auth/jaccount');
});
