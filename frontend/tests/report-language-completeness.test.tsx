import React from 'react';
import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {act,cleanup,render,screen} from '@testing-library/react';
import {FindingsPane} from '../src/components/paperLint/FindingsPane';
import {ReportProse} from '../src/i18n/ReportProse';
import {COPY,addTranslations,setLocale} from '../src/i18n/locale';
import {clearReportTranslations} from '../src/i18n/reportTranslations';
import apiClient from '../src/api';
vi.mock('../src/api',()=>({default:{post:vi.fn()}}));
const cases=[
 ['“并分配给不同设备, 减少不同测试实”中误用了英文逗号“,”，应使用中文逗号“，”。','“并分配给不同设备, 减少不同测试实”','comma'],
 ['“定理：核心定理. 设G1 与G2”中误用了英文句号“.”，应使用中文句号“。”。','“定理：核心定理. 设G1 与G2”','full stop'],
 ['“统计证据。证明. 证明的基本思路”中误用了英文句号“.”，应使用中文句号“。”。','“统计证据。证明. 证明的基本思路”','full stop'],
];
beforeEach(()=>{clearReportTranslations();setLocale('en');vi.clearAllMocks();});
afterEach(cleanup);
it.each(cases)('keeps the existing punctuation card layout and renders English instructions: %s',(message,source,kind)=>{
 const finding={finding_id:'f',rule_id:'chinese_english_symbol_mix_check',message,location:{page_number:24}};
 const run={rule_id:finding.rule_id,rule_run_id:'r',severity:'warning',outcome:'issues_found',execution_status:'completed',findings:[finding]};
 const {container}=render(<FindingsPane findings={[{key:'f',index:0,finding,ruleRun:run}] as any} rules={[{rule_id:run.rule_id,title:'中英文标点符号是否混用'}] as any} activeFindingKey={null} activeAnchorId={null} onFindingClick={()=>{}} onAnchorClick={()=>{}}/>);
 const paragraph=container.querySelector('article > p')!;
 expect(paragraph.textContent).toContain('English '+kind);expect(paragraph.textContent).not.toMatch(/中误用了|应使用/);
 expect(paragraph.textContent).toContain(source);
 expect(screen.queryByText('View original')).toBeNull();expect(container.querySelector('details')).toBeNull();
 act(()=>setLocale('zh'));expect(paragraph.textContent).toBe(message);
 act(()=>setLocale('en'));expect(paragraph.textContent).toContain('English '+kind);expect(apiClient.post).not.toHaveBeenCalled();
});
it('does not accept a mapped Chinese explanation as completed English',()=>{
 const source='这次模型输出的判断说明。';addTranslations({[source]:'依然没有翻译的判断说明。'});
 const {container}=render(<ReportProse text={source}/>);
 expect(container.textContent).not.toMatch(/\p{Script=Han}/u);expect(screen.getByText('English translation is not ready yet.')).toBeVisible();
 act(()=>addTranslations({[source]:'The explanation is ready in English.'}));expect(screen.getByText('The explanation is ready in English.')).toBeVisible();
 act(()=>setLocale('zh'));expect(screen.getByText(source)).toBeVisible();
});
it('does not accept untranslated prose merely because other words are English',()=>{
 const source='模型给出的完整说明。';addTranslations({[source]:'Reason: 仍然是中文的判断。'});
 render(<ReportProse text={source}/>);expect(screen.queryByText('Reason: 仍然是中文的判断。')).toBeNull();
 expect(screen.getByText('English translation is not ready yet.')).toBeVisible();
});
it('keeps actual source quotations in place without adding translation or UI',()=>{
 const source='关键词“安全债务治理”未对应。';const mapped='The term “安全债务治理” has no corresponding keyword.';addTranslations({[source]:mapped});
 const {container}=render(<ReportProse text={source}/>);expect(container.textContent).toBe(mapped);
 expect(container.querySelector('button,details')).toBeNull();expect(apiClient.post).not.toHaveBeenCalled();
});
it('does not allow a new untranslated quotation that was not in the source',()=>{
 const source='模型判断尚不明确。';addTranslations({[source]:'The result is “仍然无法判定”。'});
 render(<ReportProse text={source}/>);expect(screen.queryByText('The result is “仍然无法判定”。')).toBeNull();
 expect(screen.getByText('English translation is not ready yet.')).toBeVisible();
});
it('uses complete dynamic English when an approved template still contains untranslated prose',()=>{
 const source='自定义判断需要完整英文。';(COPY as Record<string,string>)[source]='另一条没有翻译的说明。';
 try {
   addTranslations({[source]:'A complete English explanation.'});render(<ReportProse text={source}/>);
   expect(screen.getByText('A complete English explanation.')).toBeVisible();expect(screen.queryByText('另一条没有翻译的说明。')).toBeNull();
 } finally {delete (COPY as Record<string,string>)[source];}
});
it('preserves a proven source literal embedded in an otherwise English finding',()=>{
 const source='请核对检测结果字段。';addTranslations({[source]:'Check the 检测结果 field.'});
 const {container}=render(React.createElement(ReportProse,{text:source,sourceLiterals:['检测结果']} as any));
 expect(container.textContent).toBe('Check the 检测结果 field.');expect(container.querySelector('button,details')).toBeNull();
});
it('keeps the exact multiline typo target while switching the surrounding explanation',()=>{
 const target='一个CVE\n漏洞在代码层面往可能涉及多个函数';const source='疑似错字：'+target;
 addTranslations({[source]:'Suspected typo: '+target});const {container}=render(<ReportProse text={source}/>);
 expect(container.textContent).toBe('Suspected typo: '+target);
 act(()=>setLocale('zh'));expect(container.textContent).toBe(source);expect(apiClient.post).not.toHaveBeenCalled();
});
