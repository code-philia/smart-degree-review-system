import {afterEach,expect,it,vi} from 'vitest';
import {render,screen} from '@testing-library/react';
import {FindingsPane} from '../src/components/paperLint/FindingsPane';
import {setLocale,translate,hasTranslation} from '../src/i18n/locale';
import {buildExportReport} from '../src/utils/reportExport/model';
import {fixture} from './fixtures/reportExport';
const message=(language:string,count:number)=>`${language}关键词共${count}个，按最新国标要求关键词为3-8个，该范围为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新。`;
const run={rule_run_id:'keyword-run',rule_id:'keyword_count_check',severity:'warning' as const,execution_status:'completed' as const,outcome:'issues_found' as const,findings:['中文','英文'].map((language,index)=>({finding_id:`keyword-${index}`,rule_id:'keyword_count_check',message:message(language,index?9:2)}))};
const items=run.findings.map((finding,index)=>({key:finding.finding_id,index,finding,ruleRun:run}));
afterEach(()=>setLocale('zh'));
it.each(['zh','en'] as const)('distinguishes Chinese and English finding headings in %s',language=>{
 setLocale(language);
 render(<FindingsPane findings={items} rules={[{rule_id:'keyword_count_check',title:'关键词数量'}] as any} activeFindingKey={items[0].key} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()}/>);
 expect(screen.getByRole('heading',{name:language==='zh'?'中文关键词数量':'Chinese keyword count',exact:true})).toBeInTheDocument();
 expect(screen.getByRole('heading',{name:language==='zh'?'英文关键词数量':'English keyword count',exact:true})).toBeInTheDocument();
 expect(screen.getByText(language==='zh'?message('中文',2):'The Chinese keyword list contains 2 keywords. The latest national standard recommends 3–8 keywords. This range is a recommendation to improve quality, not a mandatory validation requirement. The university thesis template will be updated accordingly.')).toBeInTheDocument();
});
it.each(['中文','英文'])('translates the complete %s count advisory',language=>{
 setLocale('en');expect(hasTranslation(message(language,9),'en')).toBe(true);
 expect(translate(message(language,9))).toBe(`The ${language==='中文'?'Chinese':'English'} keyword list contains 9 keywords. The latest national standard recommends 3–8 keywords. This range is a recommendation to improve quality, not a mandatory validation requirement. The university thesis template will be updated accordingly.`);
});
it('keeps the language-specific title in exported reports',()=>{
 const report={...fixture,selected_rule_ids:[run.rule_id],result:{...fixture.result,rule_runs:[run]}};
 const model=buildExportReport(report,[{rule_id:run.rule_id,title:'关键词数量'}] as any,null);
 expect(model.findings.map(f=>f.rule_title)).toEqual(['中文关键词数量','英文关键词数量']);
 expect(model.findings.map(f=>f.message)).toEqual(run.findings.map(f=>f.message));
});
