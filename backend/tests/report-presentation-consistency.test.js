import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import { genericExecutionWarnings, paperLintPresentation, flattenPaperLintFindings, numericExecutionWarnings } from '../../frontend/src/components/paperLint/model';
import { displayedReportSummary } from '../../shared/paper-lint-presentation.mjs';
const require=createRequire(import.meta.url);
const repository=require('../src/normative/paperLintReportRepository');
const {createTestDatabaseHarness}=require('../src/database/test_harness');
const harness=createTestDatabaseHarness({label:'report-presentation-consistency'});
function unavailable(id,section,message){return {rule_id:id,execution_status:'unsupported',outcome:'inconclusive',
  severity:'info',findings:[],params:{core_structure_sections:[section]},message};}

it.each([
  ['sjtu_rule_28','目录','未能检测：缺少目录，无法可靠检查目录页码。','目录'],
  ['keyword_count_check','摘要','未能检测：缺少中文摘要，无法可靠检查该摘要的关键词数量。','中文摘要'],
  ['bilingual_abstract_consistency_check','英文摘要','未能检测：英文摘要（Abstract）不完整，无法可靠比较摘要。','英文摘要'],
  ['sjtu_rule_22','主体','未能检测：缺少主体，无法可靠检查正文引文编号。','主体'],
])('gives section-specific guidance for %s instead of a service retry', (id,section,message,label)=>{
  const [warning]=genericExecutionWarnings([unavailable(id,section,message)]);
  expect(warning.suggestion).toContain(label);
  expect(warning.suggestion).not.toMatch(/稍后重试|运行记录/);
});

it('recognizes chapter prerequisites in saved reports without structured metadata',()=>{
  const run=unavailable('keyword_count_check','摘要','未能检测：缺少中文摘要，无法检查关键词数量。');
  delete run.params;
  expect(genericExecutionWarnings([run])[0].suggestion).toContain('中文摘要');
});

it('uses the missing clause to label an English thesis primary abstract',()=>{
  const run=unavailable('bilingual_abstract_consistency_check','摘要','未能检测：缺少英文摘要（Abstract），无法可靠检查中英文摘要内容一致性。');
  const suggestion=genericExecutionWarnings([run])[0].suggestion;
  expect(suggestion).toContain('英文摘要（Abstract）');
  expect(suggestion).not.toContain('中文摘要');
});

it('recognizes an incomplete legacy English abstract with its parenthetical label',()=>{
  const run=unavailable('bilingual_abstract_consistency_check','摘要','未能检测：英文摘要（Abstract）不完整，无法可靠检查中英文摘要内容一致性。');
  delete run.params;
  const suggestion=genericExecutionWarnings([run])[0].suggestion;
  expect(suggestion).toContain('补全或核对英文摘要（Abstract）');
  expect(suggestion).not.toContain('中文摘要');
});

it('does not prescribe a bibliography for a temporary reference-service failure',()=>{
  const [warning]=genericExecutionWarnings([{rule_id:'sjtu_rule_32',execution_status:'error',outcome:'inconclusive',
    severity:'warning',findings:[],message:'参考文献检索服务暂不可用，请稍后重试。'}]);
  expect(warning.suggestion).not.toContain('补充');
});

it('keeps both abstract languages in guidance for older combined missing-abstract messages',()=>{
  const run=unavailable('bilingual_abstract_consistency_check','摘要','未能检测：缺少中文摘要和英文摘要，无法比较。');
  delete run.params;
  const suggestion=genericExecutionWarnings([run])[0].suggestion;
  expect(suggestion).toContain('中文摘要');
  expect(suggestion).toContain('英文摘要');
});

it('counts an existing visible legacy finding even when its old record has no severity',()=>{
  const result={rule_runs:[{rule_id:'old_rule',execution_status:'completed',outcome:'issues_found',findings:[{finding_id:'legacy',message:'旧报告问题'}]}],summary:{}};
  expect(displayedReportSummary(result).finding_count).toBe(1);
  expect(flattenPaperLintFindings(paperLintPresentation(result))).toHaveLength(1);
});

it.each([
  [{rule_id:'required_section_completeness_check',severity:'error',execution_status:'completed',outcome:'issues_found',
    findings:[{finding_id:'a',message:'缺少中文摘要'},{finding_id:'b',message:'缺少目录'}]}, {total:2,error:2,warning:0,info:0,execution:0}],
  [{rule_id:'sjtu_rule_32',severity:'warning',execution_status:'completed',outcome:'issues_found',publication_status:'ALERT',
    findings:[{finding_id:'hidden',prompt_only:true},{finding_id:'suspected',prompt_only:true,reference_review:'supported_suspicion'}]},
    {total:1,error:0,warning:0,info:1,execution:0}],
  [{rule_id:'abstract_numeric_consistency_check',severity:'warning',execution_status:'unsupported',outcome:'inconclusive',findings:[],
    params:{preconditions:[{id:'abstract_numeric',passed:false},{id:'contribution_mapping',passed:false},{id:'experiment_subsection',passed:false,status:'skipped'}]}},
    {total:2,error:0,warning:0,info:0,execution:2}],
  [{rule_id:'abstract_numeric_consistency_check',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[],
    params:{numeric_results:[{declaration_id:'d1',status:'inconsistent',reason:'指标冲突'},{declaration_id:'d2',status:'inconclusive',reason:'统计范围不明确'},
      {declaration_id:'d3',status:'consistent',reason:'一致'},{declaration_id:'d4',status:'inconclusive',reason:'核验执行失败'}]}},
    {total:2,error:0,warning:1,info:1,execution:0}],
])('matches visible cards and warnings for report edge case %#',(run,want)=>{
  const result={rule_runs:[run],summary:{finding_count:99}};
  const summary=displayedReportSummary(result);
  expect(summary).toMatchObject({finding_count:want.total,error_finding_count:want.error,warning_finding_count:want.warning,
    info_finding_count:want.info,execution_warning_count:want.execution});
  const presentation=paperLintPresentation(result);
  const warnings=numericExecutionWarnings(run).length+genericExecutionWarnings([run]).length;
  expect(flattenPaperLintFindings(presentation).length+warnings).toBe(want.total);
  expect(paperLintPresentation(presentation)).toEqual(presentation);
});

it('returns the same displayed count from saved history and detail without rewriting stored results',async()=>{
  try{
    const db=await harness.setup();
    await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('owner','owner','hash','STUDENT','COLLEGE')");
    const result={rule_runs:[unavailable('sjtu_rule_28','目录','未能检测：缺少目录，无法可靠检查目录页码。')],
      summary:{finding_count:0,error_finding_count:0,warning_finding_count:0,info_finding_count:0,unsupported_rule_count:1,rule_count:1}};
    const raw=JSON.stringify(result);
    await db.run('INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES(?,?,?,?,?,?,?)',
      ['saved','owner','saved.pdf','unused.pdf','["sjtu_rule_28"]',raw,new Date().toISOString()]);
    const [history]=await repository.listPaperLintReportsByUser('owner');
    const detail=await repository.findPaperLintReportByIdForUser('saved','owner');
    expect(history.summary.finding_count).toBe(1);
    expect(history.summary.execution_warning_count).toBe(1);
    expect(history.summary.finding_count).toBe(paperLintPresentation(detail.result).summary.finding_count);
    expect(detail.result.summary.finding_count).toBe(0);
    expect(detail.summary.finding_count).toBe(1);
    expect((await db.get('SELECT result_json FROM paper_lint_reports WHERE id=?',['saved'])).result_json).toBe(raw);
  }finally{await harness.cleanup();}
});
