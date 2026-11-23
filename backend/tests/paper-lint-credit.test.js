import {beforeEach,afterEach,expect,it} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import express from 'express';
import request from 'supertest';
const require=createRequire(import.meta.url);
const database=require('../src/database');
const {run,get}=database;
const jobs=require('../src/normative/paperLintJobRepository');
const credit=require('../src/normative/paperLintCredit');
let harness,dir;
const paid='bilingual_keywords_correspondence_check';
const input=(userId='credit-a',selectedRuleIds=[],requestId=null)=>({userId,selectedRuleIds,requestId,
  sourceFilename:'credit.pdf',pdfBuffer:Buffer.from('%PDF-1.7\ncredit'),externalProcessingConsent:true});
beforeEach(async()=>{
  dir=await fs.mkdtemp(path.join(os.tmpdir(),'account-credit-'));
  process.env.PAPER_LINT_JOBS_DIR=path.join(dir,'jobs');
  harness=database.createTestDatabaseHarness({label:'credit'});await harness.setup();
  for(const id of ['credit-a','credit-b']) await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES (?,?,'test','STUDENT','COLLEGE')",[id,id]);
});
afterEach(async()=>{await harness.cleanup();await fs.rm(dir,{recursive:true,force:true});delete process.env.PAPER_LINT_JOBS_DIR;});

it('grants existing and new accounts exactly once across migration/restart',async()=>{
  expect(await credit.getAccountCredit('credit-a')).toMatchObject({currency:'CNY',granted_cny:'100.000000000',available_cny:'100.000000000',spent_cny:'0.000000000'});
  await run("UPDATE paper_lint_credit_accounts SET spent_nano=123456789 WHERE user_id='credit-a'");
  await database.closeDb();await database.initializeDatabase();
  expect(await credit.getAccountCredit('credit-a')).toMatchObject({available_cny:'99.876543211'});
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES ('credit-new','credit-new','test','SUPERVISOR','COLLEGE')");
  expect((await credit.getAccountCredit('credit-new')).available_cny).toBe('100.000000000');
  expect((await get('SELECT count(*) AS n FROM paper_lint_credit_accounts')).n).toBeGreaterThanOrEqual(3);
});
it('replaces the three-report cap and keeps request admission idempotent',async()=>{
  for(let i=0;i<6;i++)await jobs.createJob(input());
  const ids=await Promise.all(Array.from({length:5},()=>jobs.createJob(input('credit-a',[],'same'))));
  expect(new Set(ids).size).toBe(1);
  expect((await credit.getAccountCredit('credit-a')).available_cny).toBe('100.000000000');
  expect(await require('../src/normative/paperLintQuota').getDailyQuota('credit-a')).toMatchObject({limited:false,remaining:null});
});
it('migrates users already present before the credit schema without touching their jobs',async()=>{
  const id=await jobs.createJob(input());
  await dbDropCredit();
  await database.closeDb();await database.initializeDatabase();
  expect((await credit.getAccountCredit('credit-a')).available_cny).toBe('100.000000000');
  expect(await jobs.getJob(id)).toMatchObject({user_id:'credit-a',status:'pending'});
});
async function dbDropCredit(){
  await database.exec('DROP TRIGGER paper_lint_credit_initial_grant; DROP TABLE paper_lint_credit_calls; DROP TABLE paper_lint_credit_operations; DROP TABLE paper_lint_credit_accounts;');
}
it('retains a live worker reservation, then releases it once after exit without refunding spent tokens',async()=>{
  const id=await jobs.createJob(input('credit-a',[paid]));await jobs.claimJob(id);
  const context=await credit.beginCreditOperation(id);
  await run("UPDATE paper_lint_credit_accounts SET reserved_nano=500000,spent_nano=180000 WHERE user_id='credit-a'");
  await run(`INSERT INTO paper_lint_credit_calls(id,operation_id,rule_id,model,rate_version,rates_json,input_bound,output_bound,reserved_nano,status,worker_pid,created_at,updated_at)
    VALUES ('live',?,?,'deepseek-chat','v1','{}',100,100,500000,'reserved',?,'now','now')`,[context.operation_id,paid,process.pid]);
  await credit.finishCreditOperation(context.operation_id);
  expect((await credit.getAccountCredit('credit-a')).reserved_cny).toBe('0.000500000');
  await run("UPDATE paper_lint_credit_calls SET worker_pid=99999999 WHERE id='live'");
  await credit.finishCreditOperation(context.operation_id);await credit.finishCreditOperation(context.operation_id);
  expect(await credit.getAccountCredit('credit-a')).toMatchObject({reserved_cny:'0.000000000',spent_cny:'0.000180000'});
  expect(await get("SELECT status,failure_code FROM paper_lint_credit_calls WHERE id='live'")).toMatchObject({status:'unknown',failure_code:'worker_stopped'});
});
it('blocks only paid admission at zero balance, without role/name exemptions',async()=>{
  await run("UPDATE paper_lint_credit_accounts SET spent_nano=granted_nano WHERE user_id='credit-a'");
  await expect(jobs.createJob(input('credit-a',[paid]))).rejects.toMatchObject({status:402,code:'PAPER_LINT_CREDIT'});
  await expect(jobs.createJob(input('credit-a',['keyword_count_check']))).resolves.toBeTypeOf('string');
  await expect(jobs.createJob(input('credit-b',[paid]))).resolves.toBeTypeOf('string');
  await run("UPDATE auth_users SET role='SCHOOL_ADMIN' WHERE id='credit-a'");
  await expect(jobs.createJob(input('credit-a',[paid]))).rejects.toMatchObject({status:402});
});
it('derives operation ownership from the running job and records the exact attempt',async()=>{
  const jobId=await jobs.createJob(input('credit-a',[paid]));
  await expect(credit.beginCreditOperation(jobId)).rejects.toMatchObject({code:'CREDIT_JOB_NOT_RUNNING'});
  await jobs.claimJob(jobId);
  const context=await credit.beginCreditOperation(jobId);
  expect(context.database_file).toBe(database.getDbPath());
  const op=await get('SELECT * FROM paper_lint_credit_operations WHERE id=?',[context.operation_id]);
  expect(op).toMatchObject({user_id:'credit-a',job_id:jobId,job_attempt:1,state:'active'});
  await credit.finishCreditOperation(context.operation_id);
  expect((await get('SELECT state FROM paper_lint_credit_operations WHERE id=?',[context.operation_id])).state).toBe('closed');
});
it('keeps settled usage and the balance when the user deletes a report',async()=>{
  process.env.PAPER_LINT_REPORTS_DIR=path.join(dir,'reports');
  try{
    const reportRepository=require('../src/normative/paperLintReportRepository');
    const id=await jobs.createJob(input('credit-a',[paid]));await jobs.claimJob(id);
    const context=await credit.beginCreditOperation(id);
    await run("UPDATE paper_lint_credit_accounts SET spent_nano=180000 WHERE user_id='credit-a'");
    await run(`INSERT INTO paper_lint_credit_calls(id,operation_id,rule_id,model,rate_version,rates_json,input_bound,output_bound,reserved_nano,charged_nano,status,worker_pid,created_at,updated_at)
      VALUES ('settled',?,?,'deepseek-chat','v1','{}',100,100,500000,180000,'settled',?,'now','now')`,[context.operation_id,paid,process.pid]);
    await reportRepository.createPaperLintReport({...input('credit-a',[paid]),reportId:id,result:{type:'paper_lint',rule_runs:[],summary:{finding_count:0}}});
    await jobs.completeJob(id,id);await credit.finishCreditOperation(context.operation_id);
    expect(await reportRepository.deletePaperLintReportForUser(id,'credit-a')).toBe(true);
    expect(await get("SELECT charged_nano,status FROM paper_lint_credit_calls WHERE id='settled'")).toMatchObject({charged_nano:180000,status:'settled'});
    expect((await credit.getAccountCredit('credit-a')).spent_cny).toBe('0.000180000');
  }finally{delete process.env.PAPER_LINT_REPORTS_DIR;}
});
it('authenticates live credit and never accepts a requested account identifier',async()=>{
  const {createReviewPilotPaperLintRouter}=require('../src/normative/reviewPilotPaperLintRoutes');
  const app=express();app.use('/lint',createReviewPilotPaperLintRouter({}, {}, {}, {}));
  await request(app).get('/lint/credit').expect(401);
  const user=await get("SELECT * FROM auth_users WHERE id='credit-a'");
  const session=await require('../src/auth/sessionService').createUserSession(user);
  await run("UPDATE paper_lint_credit_accounts SET spent_nano=1000000000 WHERE user_id='credit-b'");
  await request(app).get('/lint/credit?user_id=credit-b').set('Cookie','arc_session='+session.sessionId)
    .expect(200).expect(({body,headers})=>{
      expect(body.available_cny).toBe('100.000000000');
      expect(headers['cache-control']).toContain('no-store');
    });
});
