import {createRequire} from 'node:module';
import {beforeAll,afterAll,expect,it} from 'vitest';
import express from 'express';import request from 'supertest';
import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';import {execFileSync} from 'node:child_process';
const require=createRequire(import.meta.url);
const {validateExportModel,renderReport}=require('../src/normative/reportExportService');
const {createReportExportRouter}=require('../src/normative/reportExportRoutes');
const {createTestDatabaseHarness,get}=require('../src/database');
const {createUserSession}=require('../src/auth/sessionService');
let harness,cookie;
function sample(language='zh-CN',id='report-1'){
 const en=language==='en';return {schema_version:1,reports:[{schema_version:1,language,report_id:id,
 document:{filename:'论文.pdf',title:'sample',page_count:5,word_count:100},created_at:'2026-11-11T08:30:00Z',detection_type:'review',ruleset:'v1',conclusion:en?'Some checks failed.':'部分检查失败。',
 summary:{finding_count:1,error_finding_count:0,warning_finding_count:1,info_finding_count:0,execution_warning_count:0},notice:en?'Review manually.':'请人工复核。',
 scope:[{id:'r1',title:en?'Punctuation':'标点检查',description:en?'Check punctuation.':'核对标点。'}],rules:[{id:'r1',title:en?'Punctuation':'标点检查',execution_status:'error',outcome:'inconclusive',status:en?'Failed':'执行失败',message:en?'Unavailable':'暂不可用',finding_count:1,details:[{kind:'quote',text:'原文\\input{/etc/passwd}% & # _ $'}]}],
 findings:[{number:1,id:'f1',rule_id:'r1',rule_title:en?'Punctuation':'标点检查',severity:en?'Warnings':'警告',message:en?'Review punctuation.':'请核对标点。',locations:[{label:en?'Chinese abstract source':'中文摘要原句',page:2,text:'原文,示例',marks:[{start:2,end:3}]}],suggestions:[en?'Review this finding.':'请核对本项结果。'],basis:[],evidence:['Source evidence.']}]}]};
}
beforeAll(async()=>{harness=createTestDatabaseHarness({label:'report-export',seedDefault:true});await harness.setup();const session=await createUserSession(await get("SELECT * FROM auth_users WHERE id='student01'"));cookie='arc_session='+session.sessionId;});
afterAll(async()=>harness.cleanup());
function app(generate=async()=>({content:Buffer.from('%PDF-1.7\npreview'),filename:'paper.pdf',contentType:'application/pdf'})){
 const value=express();value.use('/api/normative/paper-lint',createReportExportRouter({getReport:async(id,user)=>id==='report-1'&&user==='student01'?{id,source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'}:null,generate}));return value;
}
it('requires login and protects reports owned by another account',async()=>{
 await request(app()).post('/api/normative/paper-lint/reports/report-1/export').send({}).expect(401);
 await request(app()).post('/api/normative/paper-lint/reports/other/export').set('Cookie',cookie).send({format:'pdf',model:sample('en','other')}).expect(404);
});
it('returns a private downloadable single-language attachment after checking ownership',async()=>{
 let received;const response=await request(app(async input=>{received=input;return {content:Buffer.from('%PDF-1.7\npreview'),filename:'论文_检测报告.pdf',contentType:'application/pdf'};})).post('/api/normative/paper-lint/reports/report-1/export').set('Cookie',cookie).send({format:'pdf',model:sample()}).expect(200);
 expect(received.userId).toBe('student01');expect(received.model.reports).toHaveLength(1);expect(response.headers['cache-control']).toContain('no-store');expect(response.headers['content-disposition']).toContain('attachment');
});
it('accepts either language but rejects combined, unsupported or inconsistent documents',()=>{
 for(const language of ['zh-CN','en'])expect(validateExportModel(sample(language),'report-1').reports[0].language).toBe(language);
 for(const mutate of [m=>m.reports.push(structuredClone(m.reports[0])),m=>m.reports[0].language='fr',m=>m.reports[0].report_id='other',m=>m.reports[0].summary.finding_count=0,m=>m.reports[0].findings[0].severity='constructor',m=>m.reports[0].rules.push({...m.reports[0].rules[0]}),m=>m.reports[0].scope.push({...m.reports[0].scope[0]}),m=>m.reports[0].rules[0].status='Passed',m=>m.reports[0].findings[0].locations[0].marks=[{start:0,end:999}]]){
  const model=sample();mutate(model);expect(()=>validateExportModel(model,'report-1')).toThrowError(expect.objectContaining({status:400}));
 }
});
it('rejects null nested data and unsupported formats with structured errors',async()=>{
 for(const mutate of [m=>m.reports[0].scope[0]=null,m=>m.reports[0].rules[0]=null,m=>m.reports[0].findings[0].locations[0]=null,m=>m.reports[0].signature=null]){
  const model=sample();mutate(model);expect(()=>validateExportModel(model,'report-1')).toThrowError(expect.objectContaining({status:400}));
 }
 await request(app()).post('/api/normative/paper-lint/reports/report-1/export').set('Cookie',cookie).send({format:'html',model:sample()}).expect(400);
});
it('bounds per-user concurrency, cancels child processes and releases the renderer slot',async()=>{
 const controller=new AbortController();const report={id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'};
 const first=renderReport({userId:'cancel-user',report,model:sample(),format:'pdf',signal:controller.signal});
 await expect(renderReport({userId:'cancel-user',report,model:sample(),format:'pdf'})).rejects.toMatchObject({status:429});
 controller.abort();await expect(first).rejects.toMatchObject({name:'AbortError'});
});
it.each(['zh-CN','en'])('compiles true LaTeX in %s only, preserving source labels, symbols and highlighted spaces',{timeout:120000},async language=>{
 const symbols='Greek α β γ Δ λ ∑ ∞ ∫ ℝ 𝑥 € ± ≥ ≤ → × μ Ω Å é — 中文';
 const model=sample(language),finding=model.reports[0].findings[0];
 finding.locations[0]={...finding.locations[0],text:symbols+' alpha beta gamma delta '+ '示例'.repeat(40),marks:[{start:symbols.length+1,end:symbols.length+103}]};
 finding.message+=' \\input{/etc/passwd} & % # _ $ { } ~ ^';
 const report={id:'report-1',source_filename:'原始论文.pdf',created_at:'2026-11-11T08:30:00Z'};
 const pdf=await renderReport({userId:'unicode',report,model,format:'pdf'});
 expect(pdf.content.subarray(0,5).toString()).toBe('%PDF-');
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'export-test-'));
 try{const file=path.join(dir,'check.pdf');await fs.writeFile(file,pdf.content);const text=execFileSync(process.env.REPORT_EXPORT_PDFTOTEXT || '/usr/bin/pdftotext',['-enc','UTF-8',file,'-'],{encoding:'utf8'});
  for(const char of ['α','β','γ','λ','∑','∫','ℝ','𝑥','≥','≤','μ'])expect(text).toContain(char);
  expect(text.replace(/\s/g,'')).toContain('示例'.repeat(40));expect(text).toContain('alpha beta gamma delta');
  expect(text).toContain(language==='en'?'Chinese abstract source':'中文摘要原句');
  expect(text).toContain(language==='en'?'Thesis compliance report':'论文规范性检测报告');
  expect(text).not.toContain(language==='en'?'检测综述':'Review summary');
 }finally{await fs.rm(dir,{recursive:true,force:true});}
});
it('renders all pages into PNG images rather than truncating the attachment',{timeout:120000},async()=>{
 const images=await renderReport({userId:'image',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model:sample('en'),format:'image'});
 expect(images.content.subarray(0,2).toString()).toBe('PK');expect(images.contentType).toBe('application/zip');
});
it('uses the configured PDF inspection tool rather than a system-disk binary',{timeout:120000},async()=>{
 const previous=process.env.REPORT_EXPORT_PDFINFO;
 process.env.REPORT_EXPORT_PDFINFO='/nonexistent-export-pdfinfo';
 try{await expect(renderReport({userId:'tool-path',report:{id:'report-1',source_filename:'论文.pdf',created_at:'2026-11-11T08:30:00Z'},model:sample(),format:'pdf'})).rejects.toMatchObject({status:503});}
 finally{if(previous===undefined)delete process.env.REPORT_EXPORT_PDFINFO;else process.env.REPORT_EXPORT_PDFINFO=previous;}
});
