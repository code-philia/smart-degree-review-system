import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { AuthSessionProvider } from '../src/auth/AuthSessionProvider';
import * as authApi from '../src/api/authSession';
import apiClient from '../src/api';
import { setLocale } from '../src/i18n/locale';
import { AppearanceProvider } from '../src/AppearanceProvider';

vi.mock('../src/api/authSession', async()=>({...(await vi.importActual('../src/api/authSession')),
  fetchCurrentSession:vi.fn(),loginWithSupervisionAccount:vi.fn(),logoutCurrentSession:vi.fn()}));
vi.mock('../src/pages/NormativeCheckPage',()=>({default:()=> <h1>论文上传工作区</h1>}));
vi.mock('../src/components/NotificationBell',()=>({NotificationBell:()=>null}));
vi.mock('../src/components/paperLint/PdfPane',()=>({PdfPane:()=> <section aria-label="PDF 原文"/>}));
const admin={id:'admin',username:'admin',displayName:'管理员',role:'SCHOOL_ADMIN' as const,scope:'SCHOOL' as const,collegeId:null,supervisorId:null,accessMode:'supervision' as const};
const student={id:'jaccount:student',username:'jaccount:student',role:'STUDENT' as const,scope:'COLLEGE' as const,collegeId:null,supervisorId:null};
const reports=[{id:'report-a',source_filename:'论文甲.pdf',created_at:'2026-11-24T09:00:00Z',owner:{id:'u1',username:'student01',display_name:'学生甲'},summary:{finding_count:2,error_finding_count:0,warning_finding_count:2,info_finding_count:0}},
  {id:'report-b',source_filename:'论文乙.pdf',created_at:'2026-11-24T08:00:00Z',owner:{id:'u2',username:'student02',display_name:'学生乙'},summary:{finding_count:0,error_finding_count:0,warning_finding_count:0,info_finding_count:0}}];
const feedback=[{id:'feedback-a',type:'system',type_label:'使用反馈',username:'student01',display_name:'学生甲',satisfaction_score:2,comment:'<script>用户的原始意见</script>',feedback_label:'2 分',improvement_labels:['检测准确性'],created_at:'2026-11-24T09:00:00Z'},
  {id:'feedback-b',type:'suggestion',type_label:'修复建议评价',username:'student02',display_name:'学生乙',feedback_value:'negative',feedback_label:'点踩',reason_label:'依据不足',reason_text:'建议与原文不符',report_id:'report-b',source_filename:'论文乙.pdf',rule_title:'引用格式错误',finding_text:'原检测告警说明',generation:2,saved_suggestion:{generation:2,status:'suggested',actions:[{instruction:'这是用户点踩的已保存建议'}]},created_at:'2026-11-24T08:00:00Z'}];
const oldAdapter=apiClient.defaults.adapter;
function Location(){const location=useLocation();return <output aria-label="当前测试路径">{location.pathname}</output>;}
function mount(entry='/admin/reports'){render(<MemoryRouter initialEntries={[entry]}><AppearanceProvider><AuthSessionProvider><App/><Location/></AuthSessionProvider></AppearanceProvider></MemoryRouter>);}
beforeEach(()=>{
  localStorage.setItem('sjtu-ui-theme','light');
  window.matchMedia ||= (()=>({matches:false,media:'',onchange:null,addListener:()=>{},removeListener:()=>{},addEventListener:()=>{},removeEventListener:()=>{},dispatchEvent:()=>true})) as typeof window.matchMedia;
  setLocale('zh');vi.mocked(authApi.fetchCurrentSession).mockResolvedValue({user:admin});
  vi.mocked(authApi.logoutCurrentSession).mockResolvedValue();
  vi.mocked((authApi as any).loginWithSupervisionAccount).mockResolvedValue({user:admin});
  apiClient.defaults.adapter=async config=>{
    let data:any;
    if(config.url==='/supervision/summary')data={users:3,reports:2,feedback:2,negative_feedback:2};
    else if(config.url==='/supervision/reports'){
      const q=String(config.params?.q||'');const items=reports.filter(r=>(config.params?.search_field==='display_name'?r.owner.display_name:r.source_filename).includes(q));
      data={items,total:items.length,page:1,page_size:20};
    }else if(config.url==='/supervision/feedback'){
      const type=config.params?.type;const items=feedback.filter(f=>!type||type==='all'||type===f.type);data={items,total:items.length,page:1,page_size:20};
    }else if(config.url==='/supervision/reports/report-a')data={owner:reports[0].owner,report:{...reports[0],selected_rule_ids:['sjtu_rule_15'],result:{type:'paper_lint',paper_title:'论文甲',ruleset:{id:'test',version_label:'test'},summary:{finding_count:1,rule_count:1},rule_runs:[{rule_id:'sjtu_rule_15',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[{finding_id:'f1',message:'测试告警原文',suggestion:'保存的修改建议'}]}]}}};
    else if(config.url==='/supervision/rules')data={rules:[{rule_id:'sjtu_rule_15',title:'引用格式错误',description:'测试规则',available:true,default_severity:'warning',default_enabled:true,execution_mode:'deterministic',uses_external_model:false}]};
    else throw new Error('Unexpected API route '+config.url);
    return{data,status:200,statusText:'OK',headers:{},config};
  };
});
afterEach(()=>{apiClient.defaults.adapter=oldAdapter;vi.clearAllMocks();});

describe('Chinese read-only supervision console',()=>{
  it('provides a dedicated Chinese administrator login',async()=>{
    setLocale('en');vi.mocked(authApi.fetchCurrentSession).mockRejectedValue({response:{status:401}});mount('/admin/login');
    expect(await screen.findByRole('heading',{name:'管理员登录'})).toBeInTheDocument();
    expect(screen.getByLabelText('账号')).toBeInTheDocument();expect(screen.getByLabelText('密码')).toBeInTheDocument();
    expect(screen.queryByRole('link',{name:'使用 jAccount 登录'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:/^EN$/})).not.toBeInTheDocument();
  });
  it('routes the administrator away from the upload workflow',async()=>{
    mount('/paper-upload');expect(await screen.findByRole('heading',{name:'全部报告'})).toBeInTheDocument();
    expect(screen.getByLabelText('当前测试路径')).toHaveTextContent('/admin/reports');
    expect(screen.queryByRole('heading',{name:'论文上传工作区'})).not.toBeInTheDocument();
  });
  it('requires administrator login for a guest visiting supervision',async()=>{
    vi.mocked(authApi.fetchCurrentSession).mockRejectedValue({response:{status:401}});mount();
    expect(await screen.findByRole('heading',{name:'管理员登录'})).toBeInTheDocument();
  });
  it('keeps the actual report findings in Chinese even when the URL requests English',async()=>{
    setLocale('en');mount('/ADMIN/reports/report-a?lang=en');
    expect((await screen.findAllByText('测试告警原文')).length).toBeGreaterThan(0);
    expect(screen.queryByText('English translation is not ready yet.')).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'标记为已处理'})).not.toBeInTheDocument();
  });
  it('does not show the console to an ordinary authenticated user',async()=>{
    vi.mocked(authApi.fetchCurrentSession).mockResolvedValue({user:student});mount();
    expect(await screen.findByRole('heading',{name:'论文上传工作区'})).toBeInTheDocument();
    expect(screen.queryByRole('heading',{name:'全部报告'})).not.toBeInTheDocument();
  });
  it('switches and persists the console appearance without changing its data',async()=>{
    mount();expect(await screen.findByText('论文甲.pdf')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'切换到深色模式'}));
    await waitFor(()=>expect(document.documentElement).toHaveClass('dark'));
    expect(localStorage.getItem('sjtu-ui-theme')).toBe('dark');
    expect(screen.getByText('论文甲.pdf')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button',{name:'切换到浅色模式'}));
    await waitFor(()=>expect(document.documentElement).not.toHaveClass('dark'));
  });
  it('shows reports from different users and searches by owner',async()=>{
    mount();expect(await screen.findByText('论文甲.pdf')).toBeInTheDocument();expect(screen.getByText('论文乙.pdf')).toBeInTheDocument();
    const user=userEvent.setup();await user.selectOptions(screen.getByLabelText('报告搜索类别'),'用户姓名');await user.type(screen.getByRole('searchbox',{name:'搜索报告'}),'学生甲');
    await waitFor(()=>expect(screen.queryByText('论文乙.pdf')).not.toBeInTheDocument());
    expect(screen.getByText('论文甲.pdf')).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:/删除/})).not.toBeInTheDocument();
    expect(screen.queryByRole('button',{name:/开始检测/})).not.toBeInTheDocument();
  });
  it('opens complete feedback safely and links its exact saved suggestion version to the report',async()=>{
    mount('/admin/feedback');const user=userEvent.setup();
    expect(await screen.findByText('<script>用户的原始意见</script>')).toBeInTheDocument();
    expect(Array.from(document.scripts).some(script => script.textContent?.includes('用户的原始意见'))).toBe(false);
    await user.selectOptions(screen.getByLabelText('反馈类型'),'suggestion');
    await waitFor(()=>expect(screen.queryByText('<script>用户的原始意见</script>')).not.toBeInTheDocument());
    await user.click(screen.getByRole('button',{name:'查看反馈详情'}));
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('这是用户点踩的已保存建议')).toBeInTheDocument();
    expect(screen.getByRole('link',{name:'查看关联报告'})).toHaveAttribute('href','/admin/reports/report-b');
  });
  it('returns focus to the selected feedback details button after Escape or close',async()=>{
    mount('/admin/feedback');const user=userEvent.setup();
    await screen.findByText('建议与原文不符');
    const trigger=screen.getAllByRole('button',{name:'查看反馈详情'})[1];
    await user.click(trigger);
    expect(await screen.findByRole('dialog',{name:'反馈详情'})).toBeInTheDocument();
    await user.keyboard('{Escape}');
    await waitFor(()=>expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    await waitFor(()=>expect(trigger).toHaveFocus());
    await user.keyboard('{Enter}');
    await user.click(await screen.findByRole('button',{name:'关闭反馈详情'}));
    await waitFor(()=>expect(trigger).toHaveFocus());
  });
});
