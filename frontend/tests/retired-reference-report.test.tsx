import {afterEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen} from '@testing-library/react';
import {paperLintPresentation,flattenPaperLintFindings} from '../src/components/paperLint/model';
import {buildExportReport,buildDetectionScope,reportBlocks} from '../src/utils/reportExport/model';
import {localizeExportReport} from '../src/utils/reportExport/presentation';
import {LivePaperLintReport} from '../src/components/paperLint/LivePaperLintReport';
import {setLocale} from '../src/i18n/locale';
import {visiblePaperLintResult} from '../../shared/paper-lint-presentation.mjs';
vi.mock('../src/components/paperLint/PdfPane',()=>({PdfPane:()=>null}));
const retired='sjtu_rule_32';
const active='keyword_count_check';
const rules=[{rule_id:retired,title:'引用的外部文献不存在',description:'Reference verification'},{rule_id:active,title:'关键词数量',description:'Count keywords'}] as any;
function report(status='completed') {return {id:'saved',source_filename:'paper.pdf',created_at:'2026-11-23',selected_rule_ids:[retired,active],result:{type:'paper_lint',paper_title:'Thesis',ruleset:{name:'v1',version_label:'v1'},
 rule_runs:[{rule_id:retired,rule_run_id:'old',severity:'warning',execution_status:status,outcome:status==='completed'?'issues_found':'inconclusive',message:'隐藏的检索提示',findings:[{finding_id:'old',message:'隐藏的引用问题'}]},
 {rule_id:active,rule_run_id:'current',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[{finding_id:'keep',message:'中文关键词共2个'}]}],
 summary:{rule_count:2,completed_rule_count:status==='completed'?2:1,unsupported_rule_count:status==='unsupported'?1:0,error_rule_count:status==='error'?1:0,finding_count:99,derived_rule_count:0}}} as any;}
afterEach(()=>{cleanup();setLocale('zh');});
it('removes stale retired progress/review metadata even after its run has already been filtered',()=>{
 const source={rule_runs:[],finding_reviews:[{rule_id:retired,reason:'旧结果'}],completed_rule_ids:[retired],total_rule_ids:[retired,active],incremental:{source_report_id:'original',reused_rule_ids:[retired]}};
 const original=JSON.stringify(source);const result=visiblePaperLintResult(source);
 expect(result.finding_reviews).toEqual([]);expect(result.completed_rule_ids).toEqual([]);expect(result.total_rule_ids).toEqual([active]);
 expect(result.incremental).toEqual({source_report_id:'original',reused_rule_ids:[]});expect(JSON.stringify(source)).toBe(original);
 expect(result).not.toHaveProperty('summary');
});
it.each(['completed','unsupported','error'])('hides retired %s results and recalculates only the remaining counts without mutating input',status=>{
 const source=report(status);const original=JSON.stringify(source);const result=paperLintPresentation(source.result);
 expect(result.rule_runs.map(r=>r.rule_id)).toEqual([active]);
 expect(result.summary).toMatchObject({rule_count:1,completed_rule_count:1,unsupported_rule_count:0,error_rule_count:0,finding_count:1,warning_finding_count:1,execution_warning_count:0});
 expect(flattenPaperLintFindings(result).map(f=>f.key)).toEqual(['keep']);
 expect(paperLintPresentation(result)).toEqual(result);expect(JSON.stringify(source)).toBe(original);
});
it.each(['zh','en'])('omits retired rules from %s export content and scope',language=>{
 setLocale(language);const source=report('error');
 expect(buildDetectionScope(source,rules).map(x=>x.id)).toEqual([active]);
 const model=localizeExportReport(buildExportReport(source,rules,null),language);
 expect(model.rules.map(x=>x.id)).toEqual([active]);expect(model.findings.map(x=>x.id)).toEqual(['keep']);
 expect(JSON.stringify(reportBlocks(model))).not.toMatch(/sjtu_rule_32|引用的外部文献不存在|隐藏的检索|隐藏的引用/);
});
it('keeps a retired-only saved report usable with zero displayed results',()=>{
 const source=report();source.result.rule_runs=source.result.rule_runs.slice(0,1);source.selected_rule_ids=[retired];
 const model=buildExportReport(source,rules,null);
 expect(model.rules).toEqual([]);expect(model.scope).toEqual([]);expect(model.findings).toEqual([]);
 expect(model.summary).toMatchObject({rule_count:0,finding_count:0,execution_warning_count:0});
 expect(model.conclusion).toBe('暂无可展示的检测结果。');
 expect(localizeExportReport(model,'en').conclusion).toBe('No review results are available to display.');
});
it('hides the retired rule in the actual live report even with stale catalog and progress',()=>{
 render(<LivePaperLintReport runs={report('error').result.rule_runs} rules={rules} file={{name:'paper.pdf',url:'/paper.pdf'}} />);
 expect(screen.queryByText('隐藏的引用问题')).not.toBeInTheDocument();
 expect(screen.queryByText('隐藏的检索提示')).not.toBeInTheDocument();
});
