import {createRequire} from 'node:module';
import {expect,it} from 'vitest';
const require=createRequire(import.meta.url);
const registry=require('../rules/registry');
const service=require('../src/normative/reviewPilotPaperLintService');
const compiler=require('../src/normative/paperCompilerService');
const archive=require('../src/normative/archiveScanService');
const repository=require('../src/normative/paperLintReportRepository');
const {createTestDatabaseHarness}=require('../src/database/test_harness');
const id='sjtu_rule_32';
it.each(['scope','rules','findings'])('rejects stale %s export payloads containing a retired rule',key=>{
 const item=key==='findings'?{rule_id:id}:{id};
 expect(()=>require('../src/normative/reportExportService').validateExportModel({schema_version:1,reports:[{[key]:[item]}]},'r')).toThrow(/已下线/);
});
it('does not translate retired findings, review reasons or repair advice',()=>{
 const {extractTexts}=require('../src/normative/reportTranslationService');
 const result={rule_runs:[{rule_id:id,message:'旧引用原因',findings:[{message:'旧引用问题'}]},{rule_id:'keyword_count_check',message:'保留关键词原因'}],finding_reviews:[{rule_id:id,reason:'旧引用复核'}]};
 expect(extractTexts(result,[{rule_id:id,response:{message:'旧引用建议'}}])).toEqual(['保留关键词原因']);
});
it('removes the rule from enabled and archive/compiler catalogs and rejects stale selections before execution',async()=>{
 expect(registry.getEnabledMvpRuleIds()).not.toContain(id);
 expect(compiler.getCompilerRules().map(r=>r.rule_id)).not.toContain(id);
 expect(archive.createArchiveScanService().rules.map(r=>r.rule_id)).not.toContain(id);
 expect(()=>service.validateSelectedRuleIds({rules:[{rule_id:id,available:true}]},[id])).toThrow(/已下线/);
 await expect(compiler.runCompilerRules('unused.pdf',[id])).rejects.toMatchObject({status:400});
});
it('projects every owner history/detail without changing archived rows or other rule data',async()=>{
 const harness=createTestDatabaseHarness({label:'retired-reference-report'});
 try{
  const db=await harness.setup();
  const keep={rule_id:'keyword_count_check',severity:'warning',execution_status:'completed',outcome:'issues_found',findings:[{finding_id:'keep',message:'中文关键词共2个'}]};
  const originals=[];
  for(const owner of ['owner-a','owner-b']){
   await db.run('INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES(?,?,?,?,?)',[owner,owner,'hash','STUDENT','COLLEGE']);
   for(const status of ['completed','unsupported','error']){
    const reportId=owner+'-'+status;
    const result={rule_runs:[{rule_id:id,severity:'warning',execution_status:status,outcome:'inconclusive',message:'隐藏的检索提示',findings:[{finding_id:'retired',message:'旧引用问题'}]},keep],summary:{rule_count:2,finding_count:99,error_rule_count:1,unsupported_rule_count:1}};
    const raw=JSON.stringify(result);originals.push([reportId,raw]);
    await db.run('INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES(?,?,?,?,?,?,?)',[reportId,owner,'paper.pdf','unused.pdf',JSON.stringify([id,keep.rule_id]),raw,'2026-11-23']);
    const detail=await repository.findPaperLintReportByIdForUser(reportId,owner);
    expect(detail.result.rule_runs).toEqual([keep]);expect(detail.selected_rule_ids).toEqual([keep.rule_id]);
    expect(detail.summary).toMatchObject({finding_count:1,warning_finding_count:1,execution_warning_count:0,rule_count:1,error_rule_count:0,unsupported_rule_count:0});
    await db.run('INSERT INTO paper_lint_jobs(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,external_consent,status,progress_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
     ['job-'+reportId,owner,'paper.pdf','unused.pdf',JSON.stringify([id,keep.rule_id]),0,'failed',raw,'2026-11-23','2026-11-23']);
    const job=await require('../src/normative/paperLintJobRepository').getJobForUser('job-'+reportId,owner);
    expect(job.selected_rule_ids).toEqual([keep.rule_id]);expect(job.progress.rule_runs).toEqual([keep]);
    expect((await db.get('SELECT progress_json FROM paper_lint_jobs WHERE id=?',['job-'+reportId])).progress_json).toBe(raw);
   }
   const history=await repository.listPaperLintReportsByUser(owner);
   expect(history).toHaveLength(3);expect(history.every(r=>r.summary.finding_count===1)).toBe(true);
  }
  for(const [reportId,raw] of originals)expect((await db.get('SELECT result_json FROM paper_lint_reports WHERE id=?',[reportId])).result_json).toBe(raw);
  expect(await repository.findPaperLintReportByIdForUser('owner-a-error','owner-b')).toBeNull();
 }finally{await harness.cleanup();}
});
