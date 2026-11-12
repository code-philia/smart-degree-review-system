import {act,cleanup,render,screen,waitFor} from '@testing-library/react';
import {useSyncExternalStore} from 'react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {AuthSessionProvider,useAuthSession} from '../src/auth/AuthSessionProvider';
import * as api from '../src/api/authSession';
import {getLocale,setLocale,subscribe} from '../src/i18n/locale';
vi.mock('../src/api/authSession',async()=>({...await vi.importActual('../src/api/authSession'),fetchCurrentSession:vi.fn()}));
const account=(defaultLocale?:'zh'|'en',id='person')=>({id:'jaccount:'+id,username:'jaccount:'+id,role:'STUDENT',scope:'COLLEGE',collegeId:null,supervisorId:null,...(defaultLocale?{defaultLocale}:{})}) as api.AuthenticatedUser;
let renders:string[]=[];
function Probe(){const session=useAuthSession();const locale=useSyncExternalStore(subscribe,getLocale,getLocale);renders.push(session.status+':'+locale);return <><output>{session.status+':'+locale}</output><button onClick={()=>void session.refreshSession()}>Refresh</button></>;}
function show(){return render(<AuthSessionProvider><Probe/></AuthSessionProvider>);}
function clearChoice(){localStorage.removeItem('sjtu-ui-locale');window.dispatchEvent(new StorageEvent('storage',{key:'sjtu-ui-locale',newValue:null}));}
beforeEach(()=>{
 vi.mocked(api.fetchCurrentSession).mockReset();renders=[];
 vi.spyOn(navigator,'language','get').mockReturnValue('zh-CN');
 vi.spyOn(navigator,'languages','get').mockReturnValue(['zh-CN']);
 window.history.replaceState({},'','/paper-upload');setLocale('zh');clearChoice();
});
afterEach(()=>{cleanup();vi.restoreAllMocks();localStorage.clear();window.history.replaceState({},'','/');setLocale('zh');});
it.each(['zh','en'] as const)('applies the %s country default before authenticated content renders without recording a manual choice',async defaultLocale=>{
 vi.mocked(api.fetchCurrentSession).mockResolvedValue({user:account(defaultLocale)});show();
 await screen.findByText('authenticated:'+defaultLocale);
 expect(renders.filter(s=>s.startsWith('authenticated:'))).toEqual(expect.arrayContaining(['authenticated:'+defaultLocale]));
 expect(renders).not.toContain('authenticated:'+(defaultLocale==='en'?'zh':'en'));
 expect(localStorage.getItem('sjtu-ui-locale')).toBeNull();
 expect(document.documentElement.lang).toBe(defaultLocale==='en'?'en':'zh-CN');
});
it.each([['zh','en'],['en','zh']] as const)('keeps manual %s ahead of the %s default',async(manual,automatic)=>{
 setLocale(manual);vi.mocked(api.fetchCurrentSession).mockResolvedValue({user:account(automatic)});show();
 await screen.findByText('authenticated:'+manual);expect(getLocale()).toBe(manual);
 expect(localStorage.getItem('sjtu-ui-locale')).toBe(manual);
});
it('does not overwrite a manual choice made while authentication is in flight',async()=>{
 let resolve!:(value:api.SessionResponse)=>void;vi.mocked(api.fetchCurrentSession).mockReturnValue(new Promise(r=>{resolve=r;}));show();
 act(()=>setLocale('en'));await act(async()=>resolve({user:account('zh')}));
 expect(screen.getByText('authenticated:en')).toBeInTheDocument();
});
it('keeps explicit mail-link language ahead of a newly authenticated country default',async()=>{
 vi.mocked(api.fetchCurrentSession).mockResolvedValueOnce({user:account('en','one')}).mockResolvedValueOnce({user:account('zh','two')});
 show();await screen.findByText('authenticated:en');expect(localStorage.getItem('sjtu-ui-locale')).toBeNull();
 window.history.replaceState({},'','/reports/pdf/example?lang=en');
 await act(async()=>screen.getByRole('button',{name:'Refresh'}).click());await screen.findByText('authenticated:en');
 expect(getLocale()).toBe('en');
});
it('does not carry one automatic country default over to a different authenticated user',async()=>{
 vi.mocked(api.fetchCurrentSession).mockResolvedValueOnce({user:account('en','one')}).mockResolvedValueOnce({user:account('zh','two')});
 show();await screen.findByText('authenticated:en');await act(async()=>screen.getByRole('button',{name:'Refresh'}).click());
 await screen.findByText('authenticated:zh');expect(localStorage.getItem('sjtu-ui-locale')).toBeNull();
});
it('preserves the existing language when nationality is unavailable',async()=>{
 setLocale('en');vi.mocked(api.fetchCurrentSession).mockResolvedValue({user:account()});show();await screen.findByText('authenticated:en');
});
it('uses browser English for anonymous visitors without a choice',async()=>{
 vi.spyOn(navigator,'language','get').mockReturnValue('en-GB');vi.spyOn(navigator,'languages','get').mockReturnValue(['en-GB']);clearChoice();
 vi.mocked(api.fetchCurrentSession).mockRejectedValue(new Error('anonymous'));show();await screen.findByText('anonymous:en');
});
it('still honors manual Chinese in an English browser',async()=>{
 vi.spyOn(navigator,'language','get').mockReturnValue('en-US');vi.spyOn(navigator,'languages','get').mockReturnValue(['en-US']);setLocale('zh');
 vi.mocked(api.fetchCurrentSession).mockRejectedValue(new Error('anonymous'));show();await screen.findByText('anonymous:zh');
});
it('keeps manual choice in memory if browser storage is unavailable',async()=>{
 vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('unavailable')});setLocale('en');
 vi.mocked(api.fetchCurrentSession).mockResolvedValue({user:account('zh')});show();await screen.findByText('authenticated:en');
});
