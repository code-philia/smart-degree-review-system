import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import React from 'react';
import { act, cleanup, render, renderHook, screen, waitFor } from '@testing-library/react';
import { getLocale, setLocale, translate, clearTranslations, addTranslations } from '../src/i18n/locale';
import { jsx, preserveText } from '../src/i18n/jsx-runtime';
import { ensureReportTranslations, clearReportTranslations, useReportTranslations, assertTranslationsReady } from '../src/i18n/reportTranslations';
import apiClient from '../src/api';
import { referenceInfoFindings, referenceResourceMessage, chapterPrerequisiteSuggestion } from '../../shared/paper-lint-presentation.mjs';
import { PdfOverlay } from '../src/components/paperLint/PdfOverlay';
import { FindingsPane, RepairAction } from '../src/components/paperLint/FindingsPane';
import { EvidenceLinks } from '../src/components/paperLint/CompilerEvidence';
import { ReportHistoryTable } from '../src/components/paperLint/ReportHistoryTable';
import { MemoryRouter } from 'react-router-dom';
import { createTranslator } from '../src/i18n/locale';
vi.mock('../src/api', () => ({ default: { post: vi.fn() } }));
beforeEach(() => { clearReportTranslations(); clearTranslations(); setLocale('zh'); vi.clearAllMocks(); });
afterEach(cleanup);
it('persists locale and preserves every Chinese string exactly', () => {
  const text='  检测规则\n'; expect(translate(text)).toBe(text);
  setLocale('en'); expect(localStorage.getItem('sjtu-ui-locale')).toBe('en');
  expect(document.documentElement.lang).toBe('en'); expect(translate('检测规则')).toBe('Review checks');
  setLocale('zh'); expect(translate(text)).toBe(text);
});
it('switches mounted UI while structurally protected source and attributes remain original', () => {
  render(jsx('div', { children: [jsx('span', {children:'检测规则'}, 'ui'), preserveText(jsx('span', {title:'检测规则', children:'检测规则'}))] }));
  act(() => setLocale('en'));
  expect(screen.getByText('Review checks')).toBeTruthy();
  expect(screen.getByText('检测规则').getAttribute('title')).toBe('检测规则');
});
it('uses the current locale when an asynchronous error arrives and preserves exact dynamic keys', async () => {
  let resolve!: (text:string) => void;
  const promise=new Promise<string>(done => {resolve=done});
  function AsyncError(){const [error,setError]=React.useState(''); React.useEffect(()=>{void promise.then(setError)},[]);return jsx('p',{children:error});}
  render(React.createElement(AsyncError)); act(()=>setLocale('en'));
  await act(async()=>{resolve('报告加载失败'); await promise});
  expect(screen.getByText('Failed to load report')).toBeTruthy();
  act(()=>addTranslations({'动态解释“检测规则”':'Explanation “检测规则”'}));
  expect(translate('动态解释“检测规则”')).toBe('Explanation “检测规则”');
  expect(()=>assertTranslationsReady(['尚无映射的解释'])).toThrow();
});
it('never requests translations in Chinese and coalesces English requests', async () => {
  await ensureReportTranslations({reportId:'r1'}); expect(apiClient.post).not.toHaveBeenCalled();
  setLocale('en'); let finish!: (data:unknown)=>void;
  vi.mocked(apiClient.post).mockReturnValueOnce(new Promise(resolve=>{finish=resolve}));
  const a=ensureReportTranslations({reportId:'r1'},'v1'); const b=ensureReportTranslations({reportId:'r1'},'v1');
  expect(apiClient.post).toHaveBeenCalledTimes(1);
  finish({data:{locale:'en',status:'ready',translations:{'任意解释':'Arbitrary explanation'},source_hash:'hash',model:'qwen'}});
  await Promise.all([a,b]); expect(translate('任意解释')).toBe('Arbitrary explanation');
});
it('refreshes the live resource for revisions and saved repair updates without mutating results', async () => {
  setLocale('en'); vi.mocked(apiClient.post).mockResolvedValue({data:{locale:'en',status:'ready',translations:{},source_hash:'x',model:'qwen'}});
  const {rerender}=renderHook(({resource, revision})=>useReportTranslations(resource,revision),{initialProps:{resource:{jobId:'j1'} as {reportId?:string,jobId?:string},revision:'one'}});
  await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(1));
  rerender({resource:{jobId:'j1'},revision:'two'}); await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(2));
  rerender({resource:{reportId:'r1'},revision:'saved-repair'}); await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(3));
});
it('drops late sensitive translations after logout clear', async () => {
  setLocale('en'); let finish!: (data:unknown)=>void;
  vi.mocked(apiClient.post).mockReturnValueOnce(new Promise(resolve=>{finish=resolve}));
  const request=ensureReportTranslations({reportId:'r1'}); clearReportTranslations();
  finish({data:{locale:'en',status:'ready',translations:{'敏感解释':'Sensitive explanation'},source_hash:'x',model:'qwen'}});
  await request; expect(translate('敏感解释')).toBe('敏感解释');
});

it('localizes labels around prose independently while preserving evidence matching dictionary entries', () => {
 act(()=>setLocale('en')); addTranslations({'本次动态说明':'A dynamic explanation'});
 render(jsx('div',{children:[jsx('p',{children:['修改建议：','本次动态说明']},'suggestion'),React.createElement(EvidenceLinks,{items:[{id:'e',kind:'source_span',quote:'检测规则'}] as any})]}));
 expect(screen.getByText('A dynamic explanation',{exact:false})).toHaveTextContent('Suggested action: A dynamic explanation');
 expect(screen.getByText('检测规则')).toBeTruthy();
});
it('keeps real history filenames and attributes original with the detail arrow before its label in both locales', () => {
 const record={id:'r1',source_filename:'检测规则',created_at:'2026-11-10T00:00:00Z',summary:{finding_count:0,error_rule_count:0,unsupported_rule_count:0}} as any;
 render(React.createElement(MemoryRouter,null,React.createElement(ReportHistoryTable,{reports:[record],historyPath:'/reports',selectedReportIds:[],onSelectionChange:()=>{},deleting:false,onDelete:()=>{}})));
 const name=screen.getByText('检测规则');expect(name.getAttribute('title')).toBe('检测规则');
 let details=screen.getByRole('link',{name:'查看详情'});expect(details.firstChild?.nodeName.toLowerCase()).toBe('svg');
 act(()=>setLocale('en'));expect(screen.getByText('检测规则')).toBe(name);
 details=screen.getByRole('link',{name:'View report'});expect(details.firstChild?.nodeName.toLowerCase()).toBe('svg');
 expect(screen.getByRole('combobox',{name:'Rows per page'})).toBeTruthy();
});
it('captures locale and dynamic mappings for an in-progress export and admits translated protected quotes', () => {
 setLocale('en'); addTranslations({'解释“检测规则”':'Explanation “检测规则”'});
 const snapshot=createTranslator('en');setLocale('zh');clearTranslations();
 expect(snapshot('解释“检测规则”')).toBe('Explanation “检测规则”');expect(snapshot.has('解释“检测规则”')).toBe(true);
 expect(snapshot('检测规则')).toBe('Review checks');
});
it('shows partial/retry state and refreshes explicitly requested English work after UI switches', async () => {
 setLocale('en');vi.mocked(apiClient.post).mockResolvedValueOnce({data:{locale:'en',status:'partial',translations:{},source_hash:'1',model:'qwen'}});
 const {result}=renderHook(()=>useReportTranslations({reportId:'r1'},'repair'));
 await waitFor(()=>expect(result.current.status).toBe('partial'));
 vi.mocked(apiClient.post).mockResolvedValueOnce({data:{locale:'en',status:'ready',translations:{'后来解释':'Later explanation'},source_hash:'2',model:'qwen'}});
 act(()=>result.current.retry());await waitFor(()=>expect(result.current.status).toBe('ready'));
 setLocale('zh');vi.mocked(apiClient.post).mockResolvedValueOnce({data:{locale:'en',status:'ready',translations:{},source_hash:'3',model:'qwen'}});
 await ensureReportTranslations({reportId:'r2'},undefined,{locale:'en'});expect(apiClient.post).toHaveBeenCalledTimes(3);
});

it('restores a cached resource mapping after bounded presentation memory evicts old entries', async () => {
 setLocale('en');vi.mocked(apiClient.post).mockResolvedValueOnce({data:{locale:'en',status:'ready',translations:{'早期解释':'Earlier explanation'},source_hash:'x',model:'qwen'}});
 await ensureReportTranslations({reportId:'r/1'},'first');
 addTranslations(Object.fromEntries(Array.from({length:3001},(_,i)=>[`说明${i}`,`Explanation ${i}`])));
 expect(translate('早期解释')).toBe('早期解释');
 await ensureReportTranslations({reportId:'r/1'},'first');
 expect(apiClient.post).toHaveBeenCalledTimes(1);expect(translate('早期解释')).toBe('Earlier explanation');
});
it('keeps local reading and selection state mounted through switches', () => {
 function ReadingState(){const [page,setPage]=React.useState(3);return jsx('button',{onClick:()=>setPage(n=>n+1),children:['第 ',page,' 页']});}
 render(React.createElement(ReadingState));act(()=>screen.getByRole('button',{name:'第 3 页'}).click());
 act(()=>setLocale('en'));expect(screen.getByRole('button',{name:'Page 4'})).toBeTruthy();
 act(()=>setLocale('zh'));expect(screen.getByRole('button',{name:'第 4 页'})).toBeTruthy();
});

it('translates a complete dynamic repair instruction rather than losing its mapping during source highlighting', () => {
 setLocale('en');const instruction='请认真将“检测规则”修改为“论文格式”。其他细节保留。';
 render(React.createElement(RepairAction,{instruction}));
 act(()=>addTranslations({[instruction]:'Carefully replace “检测规则” with “论文格式”. Keep the other details.'}));
 expect(screen.getByText('Carefully replace “检测规则” with “论文格式”. Keep the other details.')).toBeTruthy();
 act(()=>setLocale('zh'));expect(screen.getByText('论文格式')).toBeTruthy();
});

it('keeps approved UI wording authoritative when a report mapping shares a UI label', () => {
 setLocale('en');addTranslations({'检测规则':'Unreviewed override'});
 expect(translate('检测规则')).toBe('Review checks');expect(createTranslator('en')('检测规则')).toBe('Review checks');
});

it('localizes the disabled check configuration reason while preserving Chinese exactly', () => {
 const reason='规则包尚未配置。';expect(translate(reason)).toBe(reason);
 setLocale('en');expect(translate(reason)).toBe('This check is not configured.');
 render(jsx('input',{type:'checkbox',disabled:true,'aria-label':reason}));
 expect(screen.getByRole('checkbox',{name:'This check is not configured.'})).toBeDisabled();
 act(()=>setLocale('zh'));expect(screen.getByRole('checkbox',{name:reason})).toBeDisabled();
});

it('serializes THREE deferred revisions of one report with only one POST in flight', async () => {
 setLocale('en');let active=0,peak=0;const finish:Array<()=>void>=[];
 vi.mocked(apiClient.post).mockImplementation(()=>{active++;peak=Math.max(peak,active);return new Promise(resolve=>finish.push(()=>{active--;resolve({data:{locale:'en',status:'ready',translations:{},source_hash:'x',model:'qwen'}})}));});
 const a=ensureReportTranslations({reportId:'slow'},'A');
 const b=ensureReportTranslations({reportId:'slow'},'B');
 const c=ensureReportTranslations({reportId:'slow'},'C');
 expect(apiClient.post).toHaveBeenCalledTimes(1);
 try {
  finish[0]();await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(2));
  expect(peak).toBe(1);finish[1]();await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(3));
  expect(peak).toBe(1);finish[2]();await Promise.all([a,b,c]);
 } finally {finish.forEach(resolve=>resolve());}
});

it('clears queued revisions on logout and keeps the new user resource tail independent of old cleanup', async () => {
 setLocale('en');const finish:Array<()=>void>=[];
 vi.mocked(apiClient.post).mockImplementation(()=>new Promise(resolve=>finish.push(()=>resolve({data:{locale:'en',status:'ready',translations:{},source_hash:'x',model:'qwen'}}))));
 const oldA=ensureReportTranslations({reportId:'same'},'old-A');
 const oldB=ensureReportTranslations({reportId:'same'},'old-B');
 clearReportTranslations();
 const newA=ensureReportTranslations({reportId:'same'},'new-A');
 const newB=ensureReportTranslations({reportId:'same'},'new-B');
 expect(apiClient.post).toHaveBeenCalledTimes(2);
 finish[0]();await Promise.all([oldA,oldB]);expect(apiClient.post).toHaveBeenCalledTimes(2);
 const newC=ensureReportTranslations({reportId:'same'},'new-C');
 finish[1]();await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(3));
 finish[2]();await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(4));
 finish[3]();await Promise.all([newA,newB,newC]);
});

it('automatically completes a bounded report across progressive 48 to 96 to 100 string batches', async () => {
 setLocale('en');const mappings=(count:number)=>Object.fromEntries(Array.from({length:count},(_,i)=>[`动态原因${i}`,`Explanation ${i}`]));
 vi.mocked(apiClient.post)
  .mockResolvedValueOnce({data:{locale:'en',status:'partial',translations:mappings(48),source_hash:'x',model:'qwen'}})
  .mockResolvedValueOnce({data:{locale:'en',status:'partial',translations:mappings(96),source_hash:'x',model:'qwen'}})
  .mockResolvedValueOnce({data:{locale:'en',status:'ready',translations:mappings(100),source_hash:'x',model:'qwen'}});
 const response=await ensureReportTranslations({reportId:'hundred'});
 expect(apiClient.post).toHaveBeenCalledTimes(3);expect(response?.status).toBe('ready');expect(translate('动态原因99')).toBe('Explanation 99');
});
it('stops partial continuation when coverage makes no progress and never retries unavailable automatically', async () => {
 setLocale('en');const partial={locale:'en',status:'partial',translations:{'动态原因':'Explanation'},source_hash:'x',model:'qwen'};
 vi.mocked(apiClient.post).mockResolvedValue({data:partial});
 const response=await ensureReportTranslations({reportId:'stalled'});
 expect(response?.status).toBe('partial');expect(apiClient.post).toHaveBeenCalledTimes(2);
 vi.mocked(apiClient.post).mockResolvedValueOnce({data:{locale:'en',status:'unavailable',translations:{},source_hash:'x',model:'qwen'}});
 await ensureReportTranslations({reportId:'unavailable'});expect(apiClient.post).toHaveBeenCalledTimes(3);
});

it('bounds progressing partial batches to eight rounds and exposes the valid progressive mappings', async () => {
 setLocale('en');let count=0;
 vi.mocked(apiClient.post).mockImplementation(async()=>{count++;return {data:{locale:'en',status:'partial',translations:Object.fromEntries(Array.from({length:count},(_,i)=>[`分批原因${i}`,`Batched reason ${i}`])),source_hash:'x',model:'qwen'}};});
 const response=await ensureReportTranslations({reportId:'large'});
 expect(apiClient.post).toHaveBeenCalledTimes(8);expect(response?.status).toBe('partial');expect(translate('分批原因7')).toBe('Batched reason 7');
});

it('localizes real PDF overlay names while preserving raw excerpt suffix and PDF geometry', () => {
 const rect={x1:10,y1:20,x2:30,y2:40,width:100,height:200,page_number:26};
 const annotations=[{findingKey:'source',ruleId:'r1',severity:'warning',pageNumber:26,boundingRect:rect,rects:[rect],textExcerpt:'检测规则'},
 {findingKey:'typo',ruleId:'r2',severity:'warning',pageNumber:33,boundingRect:rect,rects:[rect],anchorLabel:'疑似错别字'}] as any;
 const {container}=render(React.createElement(PdfOverlay,{pageNumber:26,pageWidth:100,pageHeight:200,annotations,activeFindingKey:null,activeAnchorId:null,density:'all',onFindingClick:()=>{},onAnchorClick:()=>{}}));
 const source=screen.getByRole('button',{name:'定位审查问题：检测规则'});expect(screen.getByTitle('第 26 页审查高亮')).toBeTruthy();
 const svg=container.querySelector('svg')!,geometry=svg.getAttribute('viewBox');
 act(()=>setLocale('en'));
 expect(screen.getByTitle('Review highlights on page 26')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Locate review finding: 检测规则'})).toBe(source);
 expect(screen.getByRole('button',{name:'Suspected typo: Locate page 33'})).toBeTruthy();
 expect(svg.getAttribute('viewBox')).toBe(geometry);
 act(()=>setLocale('zh'));expect(screen.getByRole('button',{name:'定位审查问题：检测规则'})).toBe(source);
});

it('covers finite reference notices and generated prerequisite instructions with no model mapping', () => {
 const notice=referenceInfoFindings({findings:[],compiler_diagnostics:[{status:'UNKNOWN',check_id:'existence',node_id:'n',reasons:[]}]})[0];
 setLocale('en');expect(translate(notice.message)).toBe('There is insufficient evidence to verify this reference. Please check it manually.');
 expect(translate(notice.suggestion)).toMatch(/^Check the reference title, authors, year and DOI/);
 for(const reason of ['QUOTA_EXHAUSTED','API_KEY not configured','reference_lookup_unavailable']){
  const message=referenceResourceMessage({rule_id:'sjtu_rule_32',message:'未触发告警',compiler_diagnostics:[{reasons:[reason]}]});
  expect(translate(message)).not.toBe(message);
 }
 const prerequisite=chapterPrerequisiteSuggestion({message:'缺少中文摘要',params:{core_structure_sections:['摘要','目录']}});
 expect(translate(prerequisite)).toBe('Add or check the following sections: Chinese abstract, contents. Make sure the content is complete and readable, then run the review again.');
 expect(translate('请补全或核对自定义章节名，确认内容完整且可读取后重新检测。')).toContain('自定义章节名');
 setLocale('zh');expect(translate(prerequisite)).toBe(prerequisite);expect(translate(notice.message)).toBe(notice.message);
});

it.each(['检测结果','提示'])('protects the literal typo correction %s while localizing the finding UI', (literal) => {
 const item={key:'typo-literal',index:0,finding:{finding_id:'typo-literal',rule_id:'typo_detection_check',message:'A typo was found.',suggestion:literal,location:null},ruleRun:{rule_run_id:'typo-run',rule_id:'typo_detection_check',severity:'warning',outcome:'issues_found',execution_status:'completed',findings:[]}} as any;
 render(React.createElement(FindingsPane,{findings:[item],rules:[{rule_id:'typo_detection_check',title:'正文错别字检测'}] as any,activeFindingKey:'typo-literal',activeAnchorId:null,onFindingClick:()=>{},onAnchorClick:()=>{}}));
 act(()=>setLocale('en'));
 expect(screen.getByRole('heading',{name:'Findings'})).toBeTruthy();
 const correction=screen.getByText(literal);expect(correction).toBeTruthy();expect(screen.getByText('Suggested action:')).toBeTruthy();
 act(()=>setLocale('zh'));expect(correction).toHaveTextContent(literal);
});
