import React from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import { FindingsPane } from '../src/components/paperLint/FindingsPane';
import { setLocale, translate, addTranslations } from '../src/i18n/locale';
import { clearReportTranslations, useReportTranslations } from '../src/i18n/reportTranslations';
import { TranslationStatus } from '../src/i18n/TranslationStatus';
import { NumericReviewDetails } from '../src/components/paperLint/NumericReviewDetails';
import { CompilerDiagnostics } from '../src/components/paperLint/CompilerEvidence';
import apiClient from '../src/api';

vi.mock('../src/api', () => ({ default: { post: vi.fn() } }));
beforeEach(() => { clearReportTranslations(); setLocale('zh'); vi.clearAllMocks(); });
afterEach(cleanup);
const chinese='这个摘要中的具体说明缺少对应的英文内容。';
const english='The English abstract omits the corresponding explanation.';
function response(translations:Record<string,string>,status='ready') {
  return {data:{locale:'en',status,translations,source_hash:'snapshot',model:'qwen'}};
}
function runs(messages=[chinese]) {
  return [{rule_id:'bilingual_abstract_consistency_check',rule_run_id:'run',severity:'warning',execution_status:'completed',outcome:'issues_found',
    findings:messages.map((message,i)=>({finding_id:'finding-'+i,rule_id:'bilingual_abstract_consistency_check',message,location:null}))}];
}
function Report({live=false,messages=[chinese]}:{live?:boolean;messages?:string[]}) {
  const ruleRuns=runs(messages);
  const status=useReportTranslations(live?{jobId:'job'}:{reportId:'report'},ruleRuns);
  return <><TranslationStatus {...status}/><FindingsPane
    findings={ruleRuns[0].findings.map((finding,index)=>({key:finding.finding_id,index,finding,ruleRun:ruleRuns[0]})) as any}
    rules={[{rule_id:'bilingual_abstract_consistency_check',title:'中英文摘要内容一致性'}] as any}
    ruleRuns={ruleRuns as any} running={live} activeFindingKey={null} activeAnchorId={null}
    onFindingClick={()=>{}} onAnchorClick={()=>{}}/></>;
}

it.each([false,true])('keeps %s live/saved English explanations English while their translation is pending', async live=>{
  let finish!:(value:unknown)=>void;
  vi.mocked(apiClient.post).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  setLocale('en'); const {container}=render(<Report live={live}/>);
  expect(screen.queryByText(chinese)).toBeNull();
  expect(screen.getByText('English translation is not ready yet.')).toBeVisible();
  const card=container.querySelector('article');
  await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(1));
  await act(async()=>{finish(response({[chinese]:english}));});
  expect(await screen.findByText(english)).toBeVisible();
  expect(container.querySelector('article')).toBe(card);
});

it('keeps Chinese exact when a pending English response arrives after switching back, then restores cached English',async()=>{
  let finish!:(value:unknown)=>void;
  vi.mocked(apiClient.post).mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  const {container}=render(<Report/>); const card=container.querySelector('article');
  expect(screen.getByText(chinese)).toBeVisible();expect(apiClient.post).not.toHaveBeenCalled();
  act(()=>setLocale('en'));expect(screen.queryByText(chinese)).toBeNull();
  await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(1));
  act(()=>setLocale('zh'));
  await act(async()=>{finish(response({[chinese]:english}));});
  expect(screen.getByText(chinese)).toBeVisible();expect(screen.queryByText(english)).toBeNull();
  act(()=>setLocale('en'));expect(screen.getByText(english)).toBeVisible();
  expect(container.querySelector('article')).toBe(card);
});

it('keeps translated live findings visible while new untranslated findings arrive',async()=>{
  setLocale('en'); const next='新的摘要说明需要对应的英文内容。'; let finish!:(value:unknown)=>void;
  vi.mocked(apiClient.post).mockResolvedValueOnce(response({[chinese]:english}))
    .mockReturnValueOnce(new Promise(resolve=>{finish=resolve;}));
  const {rerender}=render(<Report live/>);expect(await screen.findByText(english)).toBeVisible();
  rerender(<Report live messages={[chinese,next]}/>);
  expect(screen.getByText(english)).toBeVisible();expect(screen.queryByText(next)).toBeNull();
  expect(screen.getByText('English translation is not ready yet.')).toBeVisible();
  await waitFor(()=>expect(apiClient.post).toHaveBeenCalledTimes(2));
  await act(async()=>{finish(response({[chinese]:english,[next]:'A new explanation is missing from the English abstract.'}));});
  expect(await screen.findByText('A new explanation is missing from the English abstract.')).toBeVisible();
});

it('never reverts to Chinese on translation failure and supports the existing retry action',async()=>{
  setLocale('en');vi.mocked(apiClient.post).mockResolvedValueOnce(response({},'unavailable'));
  render(<Report/>);await screen.findByRole('button',{name:'Retry translation'});
  expect(screen.queryByText(chinese)).toBeNull();expect(screen.getByText('English translation is not ready yet.')).toBeVisible();
  vi.mocked(apiClient.post).mockResolvedValueOnce(response({[chinese]:english}));
  act(()=>screen.getByRole('button',{name:'Retry translation'}).click());
  expect(await screen.findByText(english)).toBeVisible();
});

it.each([
  ['缺少完整的方括号文献类型标记','The bracketed reference type code is missing or incomplete.'],
  ['目录页码 122 与正文实际页码 123 不一致','The table of contents lists page 122, but the corresponding text is on page 123.'],
  ['“EY WORDS： Compilat” 中误用了中文冒号 “：”，应使用英文冒号 “:”。','In “EY WORDS： Compilat”, a Chinese colon “：” is used instead of an English colon “:”.'],
  ['中文摘要原句','Original sentence from the Chinese abstract'],
  ['英文摘要原句','Original sentence from the English abstract'],
  ['中文摘要','Chinese abstract'],
  ['英文摘要','English abstract'],
])('immediately translates the deterministic explanation %s without a model', (source,expected)=>{
  setLocale('en');expect(translate(source)).toBe(expected);
  setLocale('zh');expect(translate(source)).toBe(source);expect(apiClient.post).not.toHaveBeenCalled();
});

it('does not leave a custom generated anchor label in Chinese during translation',()=>{
  setLocale('en');const label='这次模型生成的自定义证据位置';
  const ruleRun=runs(['An explanation.'])[0];
  const finding={...ruleRun.findings[0],anchors:[{anchor_id:'a',label,location:{page_number:1}}]};
  render(<FindingsPane findings={[{key:'finding-0',index:0,finding,ruleRun}] as any}
    rules={[]} activeFindingKey='finding-0' activeAnchorId={null} onFindingClick={()=>{}} onAnchorClick={()=>{}}/>);
  expect(screen.queryByText(label)).toBeNull();
  expect(screen.getByRole('button',{name:'English translation is not ready yet.'})).toBeVisible();
});

it('keeps numeric reasons and compiler diagnostics English before mappings arrive',()=>{
  setLocale('en');
  render(<><NumericReviewDetails run={{rule_id:'abstract_numeric_consistency_check',params:{preconditions:[{id:'abstract_numeric',passed:false,reason:chinese,suggestion:'请补充说明中的具体内容。'}]}} as any}/>
    <CompilerDiagnostics items={[{kind:'runtime',status:'UNKNOWN',message:'外部服务未完成这次具体核查。',reasons:[],evidence:[]} as any]}/></>);
  expect(screen.queryByText(chinese)).toBeNull();
  expect(screen.queryByText('外部服务未完成这次具体核查。')).toBeNull();
  expect(screen.getAllByText('English translation is not ready yet.').length).toBeGreaterThan(0);
});

it('preserves the original Chinese diagnostic delimiter and switches its English form reactively',()=>{
  const {container}=render(<CompilerDiagnostics items={[{kind:'runtime',status:'UNKNOWN',reasons:['原因甲','原因乙'],evidence:[]} as any]}/>);
  expect(container.textContent).toContain('原因甲；原因乙');
  act(()=>{addTranslations({'原因甲':'Reason A','原因乙':'Reason B'});setLocale('en');});
  expect(container.textContent).toContain('Reason A; Reason B');
  act(()=>setLocale('zh'));expect(container.textContent).toContain('原因甲；原因乙');
});
