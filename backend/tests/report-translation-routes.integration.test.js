import {afterEach,beforeEach,expect,it} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import express from 'express';
import request from 'supertest';
const require=createRequire(import.meta.url);
const {createTestDatabaseHarness}=require('../src/database/test_harness');
const {createReportTranslationRouter}=require('../src/normative/reportTranslationRoutes');
const {createTranslationService}=require('../src/normative/reportTranslationService');
const reports=require('../src/normative/paperLintReportRepository');
const jobs=require('../src/normative/paperLintJobRepository');
const harness=createTestDatabaseHarness({label:'translation'});
let db,dir,previousReportsDir,previousJobsDir,app,calls;
beforeEach(async()=>{
  dir=await fs.mkdtemp(path.join(os.tmpdir(),'translation-route-'));
  previousReportsDir=process.env.PAPER_LINT_REPORTS_DIR;
  previousJobsDir=process.env.PAPER_LINT_JOBS_DIR;
  process.env.PAPER_LINT_REPORTS_DIR=path.join(dir,'reports');
  process.env.PAPER_LINT_JOBS_DIR=path.join(dir,'jobs');
  db=await harness.setup();
  for(const user of ['owner','other']){
    await db.run('INSERT INTO auth_users (id,username,password_hash,role,scope) VALUES (?,?,?, ?,?)',[user,user,'hash','STUDENT','COLLEGE']);
    await db.run('INSERT INTO auth_sessions (id,user_id,expires_at) VALUES (?,?,?)',[user+'-session',user,'2099-01-01T00:00:00.000Z']);
  }
  await reports.createPaperLintReport({userId:'owner',sourceFilename:'原名.pdf',pdfBuffer:Buffer.from('%PDF'),selectedRuleIds:['r1'],
    reportId:'report-1',result:{paper_title:'原论文标题',rule_runs:[{rule_id:'r1',findings:[{finding_id:'f1',message:'请核对实验说明。',location:{text_excerpt:'原始证据'}}]}]}});
  calls=0;app=express();
  app.use('/api/normative/paper-lint',createReportTranslationRouter({translate:createTranslationService({
    cacheDir:path.join(dir,'cache'),model:async items=>{calls++;return {items:items.map(({id})=>({id,text:'Please check the experimental description.'}))};}
  })}));
});
afterEach(async()=>{
  await harness.cleanup();
  await fs.rm(dir,{recursive:true,force:true});
  for(const [key,value] of [['PAPER_LINT_REPORTS_DIR',previousReportsDir],['PAPER_LINT_JOBS_DIR',previousJobsDir]])
    if(value===undefined)delete process.env[key];else process.env[key]=value;
});
const url='/api/normative/paper-lint/reports/report-1/translations';
it('rejects anonymous/cross-owner access even after an owner populates persistent cache',async()=>{
  await request(app).post(url).send({locale:'en'}).expect(401);
  await request(app).post(url).set('Cookie','arc_session=owner-session').send({locale:'en'}).expect(200);
  await request(app).post(url).set('Cookie','arc_session=other-session').send({locale:'en'}).expect(404);
  expect(calls).toBe(1);
});
it('ignores no client prose: rejects extra body fields and unsupported locales',async()=>{
  await request(app).post(url).set('Cookie','arc_session=owner-session').send({locale:'en',texts:['任意内容']}).expect(400);
  await request(app).post(url).set('Cookie','arc_session=owner-session').send({locale:'zh'}).expect(400);
  expect(calls).toBe(0);
});
it('cache reuse preserves exact report result JSON and PDF bytes',async()=>{
  const before=await db.get('SELECT result_json,source_pdf_path FROM paper_lint_reports WHERE id=?',['report-1']);
  const pdf=await fs.readFile(before.source_pdf_path);
  for(let i=0;i<2;i++)await request(app).post(url).set('Cookie','arc_session=owner-session').send({locale:'en'}).expect(200).expect(({body})=>{
    expect(body).toMatchObject({locale:'en',status:'ready',model:'qwen',translations:{'请核对实验说明。':'Please check the experimental description.'}});
    expect(body.source_hash).toMatch(/^[a-f0-9]{64}$/);
  });
  const after=await db.get('SELECT result_json,source_pdf_path FROM paper_lint_reports WHERE id=?',['report-1']);
  expect(after).toEqual(before);expect(await fs.readFile(after.source_pdf_path)).toEqual(pdf);expect(calls).toBe(1);
});
it('authorizes live jobs before extracting progress',async()=>{
  const id=await jobs.createJob({userId:'owner',sourceFilename:'原名.pdf',pdfBuffer:Buffer.from('%PDF'),selectedRuleIds:['r1'],externalProcessingConsent:false});
  await jobs.claimJob(id);await jobs.updateProgress(id,{rule_runs:[{rule_id:'r1',findings:[{message:'请核对实验说明。'}]}]});
  const endpoint='/api/normative/paper-lint/jobs/'+id+'/translations';
  await request(app).post(endpoint).set('Cookie','arc_session=other-session').send({locale:'en'}).expect(404);
  await request(app).post(endpoint).set('Cookie','arc_session=owner-session').send({locale:'en'}).expect(200).expect(({body})=>expect(body.status).toBe('ready'));
});
