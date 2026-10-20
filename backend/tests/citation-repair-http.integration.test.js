import { beforeEach, afterEach, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import express from 'express';
import request from 'supertest';
const require=createRequire(import.meta.url);
const {createTestDatabaseHarness}=require('../src/database/test_harness');
const reports=require('../src/normative/paperLintReportRepository');
const {createPaperLintRepairSuggestionRouter}=require('../src/normative/paperLintRepairSuggestionRoutes');
const {createRepairSuggestionRouter}=require('../src/normative/repairSuggestionRoutes');
const harness=createTestDatabaseHarness({label:'citation-repair-http'});
const app=express();
app.use('/api/normative/paper-lint',createPaperLintRepairSuggestionRouter({modelIdentity:async()=>({model:'test-model',modelVersion:'v1'})}));
app.use('/api/normative/repair-suggestions',createRepairSuggestionRouter());
const originals={};let root;let calls;
function setEnv(key,value){originals[key]=process.env[key];process.env[key]=value;}
beforeEach(async()=>{
 root=fs.mkdtempSync(path.join(process.cwd(),'.arc-test-citation-repair-'));calls=path.join(root,'model-calls');
 const pdfRoot=path.join(root,'pdfs');fs.mkdirSync(pdfRoot);fs.writeFileSync(path.join(pdfRoot,'paper.pdf'),'%PDF-1.7');
 const model=path.join(root,'model');const extractor=path.join(root,'extractor');
 fs.writeFileSync(extractor,`#!${process.execPath}\nprocess.stdout.write(JSON.stringify({text:'已保存PDF位置附近的原文引用 [1]',page_number:1}));\n`,{mode:0o700});
 fs.writeFileSync(model,`#!${process.execPath}\nif(process.argv.includes('--info')){process.stdout.write(JSON.stringify({model:'test-model',modelVersion:'v1'}));}else{let text='';process.stdin.on('data',x=>text+=x);process.stdin.on('end',()=>{const input=JSON.parse(JSON.parse(text).messages[1].content);require('fs').appendFileSync(${JSON.stringify(calls)},'call\\n');process.stdout.write(JSON.stringify({model:'test-model',modelVersion:'v1',answer:{status:'suggested',actions:[{instruction:'依据已提供内容核对引用',evidence_ids:[input.evidence[0].evidence_id]}]},usage:{input_tokens:10,output_tokens:10,attempts:1}}));});}\n`,{mode:0o700});
 setEnv('PAPER_LINT_REPORTS_DIR',path.join(root,'reports'));setEnv('ARCHIVE_SCAN_ROOT',pdfRoot);
 setEnv('REPAIR_MODEL_PYTHON',model);setEnv('REPAIR_EVIDENCE_PYTHON',extractor);
 const db=await harness.setup();
 for(const [id,role] of [['owner','STUDENT'],['other','STUDENT'],['admin','SCHOOL_ADMIN']]){
  await db.run('INSERT INTO auth_users (id,username,password_hash,role,scope) VALUES (?,?,?,?,?)',[id,id,'hash',role,'SCHOOL']);
  await db.run('INSERT INTO auth_sessions (id,user_id,expires_at) VALUES (?,?,?)',[id+'-session',id,'2099-01-01T00:00:00.000Z']);
 }
 const runs=['31','32','33'].map(id=>({rule_id:'sjtu_rule_'+id,package_sha256:'test-package',findings:[{
  finding_id:'finding-'+id,message:'待核对的引用问题',location:{type:'pdf_bbox',page_number:1,text_excerpt:'原文引用 [1]'},anchors:[],
  evidence:[{id:'content',kind:'external_source',quote:'受控用例中的被引文献内容'}],
 }]}));
 runs.push({rule_id:'required_section_completeness_check',params:{required_sections:['参考文献']},findings:[{finding_id:'missing-reference',message:'缺少参考文献章节',location:null,anchors:[]}]});
 await reports.createPaperLintReport({userId:'owner',sourceFilename:'paper.pdf',pdfBuffer:Buffer.from('%PDF-1.7'),selectedRuleIds:runs.map(r=>r.rule_id),result:{rule_runs:runs},reportId:'citation-report'});
 await db.run("INSERT INTO archive_scan_jobs(id,created_by,selected_rule_ids_json,status,total_count) VALUES('job','admin','[]','completed',1)");
 await db.run("INSERT INTO archive_scan_documents(id,job_id,relative_path,filename,size_bytes,status,result_json) VALUES('doc','job','paper.pdf','paper.pdf',1,'completed',?)",[JSON.stringify({rule_runs:runs})]);
});
afterEach(async()=>{
 await harness.cleanup();
 for(const [key,value] of Object.entries(originals)){if(value===undefined)delete process.env[key];else process.env[key]=value;delete originals[key];}
 fs.rmSync(root,{recursive:true,force:true});
});
function count(){return fs.existsSync(calls)?fs.readFileSync(calls,'utf8').split('call').length-1:0;}
it.each(['31','32','33'])('generates, saves, reuses and force-regenerates owner-scoped rule%s advice',async id=>{
 const url='/api/normative/paper-lint/reports/citation-report/repair-suggestions';
 const body={rule_id:'sjtu_rule_'+id,finding_id:'finding-'+id};
 await request(app).post(url).set('Cookie','arc_session=owner-session').send(body).expect(201).expect(({body})=>expect(body.cached).toBe(false));
 expect(count()).toBe(1);
 await request(app).post(url).set('Cookie','arc_session=owner-session').send(body).expect(200).expect(({body})=>expect(body.cached).toBe(true));
 expect(count()).toBe(1);
 await request(app).get(url).query(body).set('Cookie','arc_session=owner-session').expect(200).expect(({body})=>expect(body.response.status).toBe('suggested'));
 await request(app).get(url).query(body).set('Cookie','arc_session=other-session').expect(404);
 await request(app).post(url).set('Cookie','arc_session=owner-session').send({...body,force:true}).expect(201);
 expect(count()).toBe(2);
});
it.each(['31','32','33'])('generates and reuses administrator archive rule%s advice',async id=>{
 const base='/api/normative/repair-suggestions/archive-findings';const body={job_id:'job',document_id:'doc',rule_id:'sjtu_rule_'+id,finding_id:'finding-'+id};
 await request(app).post(base+'/evaluate').set('Cookie','arc_session=owner-session').send(body).expect(403);
 await request(app).post(base+'/evaluate').set('Cookie','arc_session=admin-session').send(body).expect(201);
 expect(count()).toBe(1);
 await request(app).post(base+'/evaluate').set('Cookie','arc_session=admin-session').send(body).expect(200).expect(({body})=>expect(body.cached).toBe(true));
 expect(count()).toBe(1);
 await request(app).get(base).query(body).set('Cookie','arc_session=admin-session').expect(200).expect(({body})=>expect(body.suggestions).toHaveLength(1));
});

it('force-regenerates archive advice and uses the newest saved version afterward',async()=>{
 const url='/api/normative/repair-suggestions/archive-findings/evaluate';const body={job_id:'job',document_id:'doc',rule_id:'sjtu_rule_31',finding_id:'finding-31'};
 await request(app).post(url).set('Cookie','arc_session=admin-session').send(body).expect(201);
 await request(app).post(url).set('Cookie','arc_session=admin-session').send({...body,force:true}).expect(201);
 expect(count()).toBe(2);
 await request(app).post(url).set('Cookie','arc_session=admin-session').send(body).expect(200).expect(({body})=>expect(body.cached).toBe(true));
 expect(count()).toBe(2);
});
it.each(['archive','report'])('coalesces concurrent automatic %s requests without extra model calls',async kind=>{
 const url=kind==='archive'?'/api/normative/repair-suggestions/archive-findings/evaluate':'/api/normative/paper-lint/reports/citation-report/repair-suggestions';
 const body={job_id:'job',document_id:'doc',rule_id:'sjtu_rule_31',finding_id:'finding-31'};const cookie=kind==='archive'?'arc_session=admin-session':'arc_session=owner-session';
 const responses=await Promise.all([request(app).post(url).set('Cookie',cookie).send(body),request(app).post(url).set('Cookie',cookie).send(body)]);
 expect(responses.every(x=>[200,201].includes(x.status))).toBe(true);expect(count()).toBe(1);
});

it('supports a basic-rule alarm without inventing a PDF location',async()=>{
 const url='/api/normative/paper-lint/reports/citation-report/repair-suggestions';const body={rule_id:'required_section_completeness_check',finding_id:'missing-reference'};
 await request(app).post(url).set('Cookie','arc_session=owner-session').send(body).expect(201);expect(count()).toBe(1);
 await request(app).get(url).query(body).set('Cookie','arc_session=owner-session').expect(200).expect(({body})=>expect(body.response.status).toBe('suggested'));
 await request(app).post(url).set('Cookie','arc_session=owner-session').send(body).expect(200);expect(count()).toBe(1);
 await request(app).get(url).query(body).set('Cookie','arc_session=other-session').expect(404);
});
