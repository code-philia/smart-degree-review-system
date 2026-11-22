import {createRequire} from 'node:module';
import {expect,it} from 'vitest';
const require=createRequire(import.meta.url);
const repository=require('../src/normative/paperLintReportRepository');
const {createTestDatabaseHarness}=require('../src/database/test_harness');
const harness=createTestDatabaseHarness({label:'reference-advisory-copy'});
const oldMessage='文献类型或载体标记不在国标代码表中';
const oldSuggestion='请按实际著录资源核对并补齐类型标记；期刊用[J]、会议论文用[C]等，不能仅凭访问网址改变资源类型。';
const message='按最新参考文献标准GB/T 7714-2025，文献类型或载体标记不在国标代码表中';
const suggestion='可按最新国家标准根据实际著录资源核对并补齐类型标记，所有参考文献标准统一用GB/T 7714-2025或GB/T 7714-2015，该检测项为质量优化建议，不属于强制校验红线，后续学校模版会做同步更新';
it('projects saved defaults without rewriting stored JSON or unrelated fields',async()=>{
 try{
  const db=await harness.setup();
  await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('owner','owner','hash','STUDENT','COLLEGE')");
  const finding={finding_id:'f',message:oldMessage,suggestion:oldSuggestion,location:{type:'pdf_page',page_number:27},anchors:[]};
  const result={rule_runs:[{rule_id:'sjtu_rule_31',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[finding,
   {...finding,finding_id:'missing',message:'缺少完整的方括号文献类型标记'},
   {...finding,finding_id:'custom',suggestion:'保留已确认的具体修改建议。'}]},
   {rule_id:'other',severity:'info',execution_status:'completed',outcome:'issues_found',findings:[{...finding,finding_id:'other'}]}],summary:{}};
  const raw=JSON.stringify(result);
  await db.run('INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES(?,?,?,?,?,?,?)',
    ['saved','owner','saved.pdf','unused.pdf','["sjtu_rule_31"]',raw,new Date().toISOString()]);
  const response=await repository.findPaperLintReportByIdForUser('saved','owner');
  const findings=response.result.rule_runs[0].findings;
  expect(findings[0]).toEqual({...finding,message,suggestion});
  expect(findings[1].message).toBe('缺少完整的方括号文献类型标记');expect(findings[1].suggestion).toBe(suggestion);
  expect(findings[2].suggestion).toBe('保留已确认的具体修改建议。');
  expect(response.result.rule_runs[0].severity).toBe('warning');
  expect(response.result.rule_runs[1]).toEqual(result.rule_runs[1]);
  expect((await db.get('SELECT result_json FROM paper_lint_reports WHERE id=?',['saved'])).result_json).toBe(raw);
 }finally{await harness.cleanup();}
});
