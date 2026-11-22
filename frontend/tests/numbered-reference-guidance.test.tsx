import {afterEach,expect,it,vi} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {chapterPrerequisiteSuggestion} from '../../shared/paper-lint-presentation.mjs';
import {genericExecutionWarnings} from '../src/components/paperLint/model';
import {FindingsPane} from '../src/components/paperLint/FindingsPane';
import {setLocale,translate} from '../src/i18n/locale';
import {buildExportReport} from '../src/utils/reportExport/model';
import {fixture} from './fixtures/reportExport';

const reason='未可靠识别编号参考文献表';
const suggestion='请按国标要求对参考文献列表进行编号，确认内容完整且可读取后重新检测。';
const english='Number the reference list according to the national standard. Make sure the content is complete and readable, then run the review again.';
const run=(id='sjtu_rule_22')=>({rule_id:id,rule_run_id:'run',severity:'warning' as const,
 execution_status:'unsupported' as const,outcome:'inconclusive' as const,message:reason,findings:[]});
afterEach(()=>{cleanup();setLocale('zh');});
it.each(['sjtu_rule_22','sjtu_rule_24','sjtu_rule_31','sjtu_rule_32','sjtu_rule_33'])('uses explicit numbering advice for %s without mutating saved input',id=>{
 const source=run(id);const before=JSON.stringify(source);
 expect(chapterPrerequisiteSuggestion(source)).toBe(suggestion);
 expect(genericExecutionWarnings([source])[0].suggestion).toBe(suggestion);
 expect(JSON.stringify(source)).toBe(before);
});
it('also applies to warnings with structured bibliography prerequisite metadata',()=>{
 expect(chapterPrerequisiteSuggestion({...run(),params:{core_structure_sections:['参考文献']}} as any)).toBe(suggestion);
});
it.each(['zh','en'] as const)('renders the actual warning card with the requested %s advice',locale=>{
 setLocale(locale);const source=run();const warnings=genericExecutionWarnings([source]);
 render(<FindingsPane findings={[]} rules={[{rule_id:source.rule_id,title:'正文引文引用编号缺失'}] as any}
  ruleRuns={[source]} selectedRuleIds={[source.rule_id]} activeFindingKey={null} activeAnchorId={null}
  onFindingClick={vi.fn()} onAnchorClick={vi.fn()} executionWarnings={warnings}/>);
 expect(screen.getByText(locale==='zh'?suggestion:english)).toBeInTheDocument();
});
it('uses the same numbering advice in exported warning records',()=>{
 const report=structuredClone(fixture);report.result.rule_runs=[run()];report.selected_rule_ids=['sjtu_rule_22'];
 const exported=buildExportReport(report,[{rule_id:'sjtu_rule_22',title:'正文引文引用编号缺失'}] as any);
 expect(JSON.stringify(exported)).toContain(suggestion);
});
it('has a complete deterministic English translation',()=>{
 setLocale('en');expect(translate(suggestion)).toBe(english);
});
it('keeps other chapter and reference failures unchanged',()=>{
 expect(chapterPrerequisiteSuggestion({...run(),message:'缺少参考文献'})).toBe('请补齐或核对参考文献，确认内容完整且可读取后重新检测。');
 expect(chapterPrerequisiteSuggestion({...run('keyword_count_check'),message:'缺少中文摘要'})).toBe('请补齐或核对中文摘要，确认内容完整且可读取后重新检测。');
 expect(chapterPrerequisiteSuggestion({...run(),message:'参考文献检索服务暂不可用，请稍后重试。'})).toBeNull();
 expect(chapterPrerequisiteSuggestion(run('keyword_count_check'))).not.toBe(suggestion);
 expect(chapterPrerequisiteSuggestion({...run('sjtu_rule_32'),params:{reference_resources_unavailable:true}} as any)).not.toBe(suggestion);
});
