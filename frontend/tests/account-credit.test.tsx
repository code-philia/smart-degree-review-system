import {act,fireEvent,render,renderHook,screen,waitFor} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {CreditBalance,CreditPrice,CreditEstimate} from '../src/components/paperLint/PaperLintCredit';
import {usePaperLintCredit} from '../src/hooks/usePaperLintCredit';
import {fetchPaperLintCredit} from '../src/api/paperLint';
import {setLocale} from '../src/i18n/locale';
import {ThesisUploadPanel} from '../src/components/paperLint/ThesisUploadPanel';
vi.mock('../src/api/paperLint',async()=>({...await vi.importActual('../src/api/paperLint'),fetchPaperLintCredit:vi.fn()}));
const sample=(user_id='alice',extra={})=>({user_id,currency:'CNY',policy_version:'test',granted_cny:'100.000000000',spent_cny:'75.000000000',reserved_cny:'0.000000000',available_cny:'25.000000000',remaining_percent:25,estimated_cny:{},server_time:'now',...extra});
beforeEach(()=>{setLocale('zh');vi.mocked(fetchPaperLintCredit).mockResolvedValue(sample());});
afterEach(()=>{vi.clearAllMocks();vi.useRealTimers();setLocale('zh');});
it('renders the live ring and available percentage beside its label, rather than hardcoded preview values',async()=>{
  render(<CreditBalance credit={sample()} />);
  const trigger=screen.getByRole('button',{name:/25.00/});
  expect(trigger).toHaveTextContent('¥25.00');
  expect(trigger.querySelector('.credit-ring-progress')).toHaveAttribute('stroke-dashoffset','75');
  expect(trigger.querySelector('.credit-balance-ring text')).toBeNull();
  fireEvent.click(trigger);
  expect(await screen.findByText('当前可用（25%）')).toBeVisible();
  expect(screen.getByText('¥75.00')).toBeVisible();
});
it('keeps English labels and the approved estimated prices synchronized',async()=>{
  setLocale('en');
  render(<><CreditBalance credit={sample()} /><CreditPrice ruleId="bilingual_keywords_correspondence_check"/><CreditPrice ruleId="chinese_english_symbol_mix_check"/><CreditEstimate selectedRuleIds={['typo_detection_check','abstract_numeric_consistency_check']} /></>);
  fireEvent.click(screen.getByRole('button',{name:/25.00/}));
  expect(await screen.findByText('Available (25%)')).toBeVisible();
  expect(screen.getByText('Est. ¥0.01')).toBeVisible();
  expect(screen.getByText('¥0.15')).toBeVisible();
  expect(document.querySelectorAll('.credit-rule-price')).toHaveLength(1);
});
it('never invents a balance while loading and offers retry after a failure',()=>{
  const retry=vi.fn();const view=render(<CreditBalance credit={null}/>);
  expect(screen.getByRole('button')).toHaveTextContent('—');
  expect(screen.queryByText('100.00')).not.toBeInTheDocument();
  view.rerender(<CreditBalance credit={null} unavailable onRetry={retry}/>);
  fireEvent.click(screen.getByRole('button'));expect(retry).toHaveBeenCalledOnce();
});
it('drops stale account responses and rejects an authenticated response belonging to a different account',async()=>{
  let oldResolve:(v:any)=>void=()=>{};
  vi.mocked(fetchPaperLintCredit).mockImplementationOnce(()=>new Promise(resolve=>{oldResolve=resolve;})).mockResolvedValue(sample('bob',{available_cny:'12.000000000'}));
  const view=renderHook(({owner})=>usePaperLintCredit(owner,false),{initialProps:{owner:'alice'}});
  view.rerender({owner:'bob'});
  await waitFor(()=>expect(view.result.current.credit?.available_cny).toBe('12.000000000'));
  await act(async()=>oldResolve(sample('alice')));
  expect(view.result.current.credit?.user_id).toBe('bob');
  vi.mocked(fetchPaperLintCredit).mockResolvedValue(sample('alice'));
  await act(async()=>await view.result.current.refresh());
  expect(view.result.current.error).toBe(true);
  expect(view.result.current.credit?.user_id).toBe('bob');
});
it('refreshes active deductions, focus and cross-tab changes without mixing accounts',async()=>{
  const view=renderHook(()=>usePaperLintCredit('alice',true));
  await waitFor(()=>expect(view.result.current.credit?.available_cny).toBe('25.000000000'));
  vi.mocked(fetchPaperLintCredit).mockResolvedValue(sample('alice',{available_cny:'24.990000000'}));
  await act(async()=>window.dispatchEvent(new Event('focus')));
  await waitFor(()=>expect(view.result.current.credit?.available_cny).toBe('24.990000000'));
  vi.mocked(fetchPaperLintCredit).mockResolvedValue(sample('alice',{available_cny:'24.980000000'}));
  await act(async()=>window.dispatchEvent(new StorageEvent('storage',{key:'paper-lint-active-job:alice'})));
  await waitFor(()=>expect(view.result.current.credit?.available_cny).toBe('24.980000000'));
});
it('allows a free selection at zero credit but disables a new paid selection',()=>{
  const rules=['chinese_english_symbol_mix_check','typo_detection_check'].map(rule_id=>({rule_id,title:rule_id,description:'test',available:true,
    default_severity:'warning' as const,default_enabled:true,execution_mode:'deterministic' as const,uses_external_model:rule_id==='typo_detection_check'}));
  const props={rules,selectedRuleIds:['chinese_english_symbol_mix_check'],onSelectionChange:vi.fn(),
    file:new File(['%PDF-1.7'],'paper.pdf',{type:'application/pdf'}),onChooseFile:vi.fn(),catalogLoading:false,catalogReady:true,
    catalogError:null,onReloadCatalog:vi.fn(),running:false,stopping:false,stopped:false,canStop:false,onStop:vi.fn(),onStart:vi.fn(),
    error:null,uploadPercent:null,jobStatus:null,jobProgress:null,activeFilename:null,
    credit:sample('alice',{available_cny:'0.000000000',remaining_percent:0})};
  const view=render(<ThesisUploadPanel {...props}/>);
  expect(screen.getByRole('button',{name:'开始检测',exact:true})).toBeEnabled();
  view.rerender(<ThesisUploadPanel {...props} selectedRuleIds={['typo_detection_check']}/>);
  expect(screen.getByRole('button',{name:'开始检测',exact:true})).toBeDisabled();
  view.rerender(<ThesisUploadPanel {...props} selectedRuleIds={['typo_detection_check']} quotaRetryAllowed/>);
  expect(screen.getByRole('button',{name:'开始检测',exact:true})).toBeEnabled();
});
it('polls an active account balance and stops polling after unmount',async()=>{
  vi.useFakeTimers();
  const view=renderHook(()=>usePaperLintCredit('alice',true));
  await act(async()=>{});
  expect(view.result.current.credit?.available_cny).toBe('25.000000000');
  vi.mocked(fetchPaperLintCredit).mockResolvedValue(sample('alice',{available_cny:'24.990000000'}));
  await act(async()=>{await vi.advanceTimersByTimeAsync(2000);});
  expect(view.result.current.credit?.available_cny).toBe('24.990000000');
  view.unmount();const count=vi.mocked(fetchPaperLintCredit).mock.calls.length;
  await act(async()=>{await vi.advanceTimersByTimeAsync(30000);});
  expect(fetchPaperLintCredit).toHaveBeenCalledTimes(count);
});
