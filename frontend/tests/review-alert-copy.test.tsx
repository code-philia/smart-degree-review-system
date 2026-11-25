import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {FindingsPane} from '../src/components/paperLint/FindingsPane';
import {genericExecutionWarnings,numericExecutionWarnings,paperLintFeedbackItems} from '../src/components/paperLint/model';
import {setLocale,translate} from '../src/i18n/locale';
import {buildExportReport,reportBlocks} from '../src/utils/reportExport/model';
import {localizeExportReport} from '../src/utils/reportExport/presentation';
import {fixture} from './fixtures/reportExport';
const message='请稍后重试；若持续失败，请联系管理员检查运行记录，联系邮箱：j82279240@gmail.com';
const english='Try again later. If the problem persists, contact the administrator to check the run logs. Contact email: j82279240@gmail.com';
const run={rule_id:'bilingual_keywords_correspondence_check',rule_run_id:'run',severity:'info' as const,execution_status:'unsupported' as const,outcome:'inconclusive' as const,findings:[],
 message:'API 资源暂不可用，部分关键词核验未完成。',params:{}};
afterEach(()=>{cleanup();setLocale('zh');});
it('provides the exact contact advice for generic resource failures',()=>{
 const source=structuredClone(run),before=JSON.stringify(source);
 expect(genericExecutionWarnings([source])[0].suggestion).toBe(message);
 expect(JSON.stringify(source)).toBe(before);
 expect(paperLintFeedbackItems({rule_runs:[source]})[0].key).toBe('execution-warning:bilingual_keywords_correspondence_check:generic');
});
it('includes the same email for numeric API failures',()=>{
 expect(numericExecutionWarnings({...run,rule_id:'abstract_numeric_consistency_check',execution_status:'error',params:{failure:{error_type:'HTTPError',message:'HTTP 429'}}} as any)[0].suggestion).toBe(message);
});
it.each(['zh','en'] as const)('renders the renamed %s alert category and contact advice',locale=>{
 setLocale(locale);
 const {container}=render(<FindingsPane findings={[]} rules={[{rule_id:run.rule_id,title:'中英文关键词对应'}] as any}
  ruleRuns={[run]} selectedRuleIds={[run.rule_id]} activeFindingKey={null} activeAnchorId={null} onFindingClick={vi.fn()} onAnchorClick={vi.fn()}
  executionWarnings={genericExecutionWarnings([run])}/>);
 expect(screen.getByText(locale==='zh'?message:english)).toBeInTheDocument();
 expect(screen.getByRole('button',{name:locale==='zh'?'检测异常提醒 1':/review alert/i})).toHaveTextContent(locale==='zh'?'检测异常提醒 1':'Review alerts 1');
 expect(container.textContent).not.toContain('规则未实现警告');expect(container.textContent).not.toContain('Unverified');
});
it('uses renamed severities and contact advice in Chinese and English exports',()=>{
 const report=structuredClone(fixture);report.result.rule_runs=[run];report.selected_rule_ids=[run.rule_id];
 const model=buildExportReport(report,[{rule_id:run.rule_id,title:'中英文关键词对应'}] as any);
 expect(model.findings[0].severity).toBe('检测异常提醒');expect(model.findings[0].suggestions).toContain(message);
 const en=localizeExportReport(model,'en');expect(en.findings[0].severity).toBe('Review alerts');expect(en.findings[0].suggestions).toContain(english);
 expect(reportBlocks(en).map(b=>b.text).join('\n')).not.toContain('Unverified');
});
it('translates the contact advice and preserves specific prerequisite guidance',()=>{
 setLocale('en');expect(translate(message)).toBe(english);expect(translate('检测异常提醒数')).toBe('Review alerts');
 const prerequisite={...run,rule_id:'sjtu_rule_22',message:'未可靠识别编号参考文献表',params:{}};
 expect(genericExecutionWarnings([prerequisite])[0].suggestion).toBe('请按国标要求对参考文献列表进行编号，确认内容完整且可读取后重新检测。');
});
