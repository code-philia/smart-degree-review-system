import {beforeEach,afterEach,expect,it,vi} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
import express from 'express';import request from 'supertest';
const require=createRequire(import.meta.url);
const {createTestDatabaseHarness,run,get,all}=require('../src/database');
const jobs=require('../src/normative/paperLintJobRepository');
const reports=require('../src/normative/paperLintReportRepository');
let harness,directory;
const pdf=Buffer.from('%PDF-1.7\nquota fixture');
const args=(userId='quota-student',requestId=null)=>({userId,sourceFilename:'论文.pdf',pdfBuffer:pdf,selectedRuleIds:[],requestId});
const quota=(userId='quota-student',now)=>require('../src/normative/paperLintQuota').getDailyQuota(userId,now);
async function completed(userId='quota-student',requestId=null){
 const id=await jobs.createJob(args(userId,requestId));await jobs.claimJob(id);
 await reports.createPaperLintReport({userId,sourceFilename:'论文.pdf',pdfBuffer:pdf,selectedRuleIds:[],reportId:id,result:{type:'paper_lint',rule_runs:[],summary:{finding_count:0}}});
 expect(await jobs.completeJob(id,id)).toBe(true);return id;
}
beforeEach(async()=>{
 vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(new Date('2026-11-12T02:00:00.000Z'));
 directory=await fs.mkdtemp(path.join(os.tmpdir(),'daily-quota-'));
 process.env.PAPER_LINT_JOBS_DIR=path.join(directory,'jobs');process.env.PAPER_LINT_REPORTS_DIR=path.join(directory,'reports');
 harness=createTestDatabaseHarness({label:'daily-quota'});await harness.setup();
 for(const [id,role] of [['quota-student','STUDENT'],['quota-supervisor','SUPERVISOR'],['quota-admin','SCHOOL_ADMIN'],['quota-college','COLLEGE_ADMIN']])
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES (?,?,'test',?,'COLLEGE')",[id,id,role]);
});
afterEach(async()=>{await harness.cleanup();await fs.rm(directory,{recursive:true,force:true});delete process.env.PAPER_LINT_JOBS_DIR;delete process.env.PAPER_LINT_REPORTS_DIR;vi.useRealTimers();});

it('rejects the fourth ordinary-user report after three saved reports',async()=>{
 for(let n=0;n<3;n++)await completed();
 await expect(jobs.createJob(args())).rejects.toMatchObject({status:429});
 expect(await all("SELECT id FROM paper_lint_jobs WHERE user_id='quota-student'")).toHaveLength(3);
 expect(await quota()).toMatchObject({limited:true,limit:3,used:3,reserved:0,remaining:0,timezone:'Asia/Shanghai'});
});
it('reserves only three concurrent requests atomically and cleans rejected PDF files',async()=>{
 const results=await Promise.allSettled(Array.from({length:10},(_,n)=>jobs.createJob(args('quota-student','concurrent-'+n))));
 expect(results.filter(x=>x.status==='fulfilled')).toHaveLength(3);
 expect(results.filter(x=>x.status==='rejected')).toHaveLength(7);
 for(const item of results)if(item.status==='rejected')expect(item.reason.status).toBe(429);
 expect(await fs.readdir(process.env.PAPER_LINT_JOBS_DIR)).toHaveLength(3);
 expect(await quota()).toMatchObject({used:0,reserved:3,remaining:0});
});
it('releases a reservation on failure or successful cancellation without consuming a success',async()=>{
 const one=await jobs.createJob(args()),two=await jobs.createJob(args()),three=await jobs.createJob(args());
 await jobs.claimJob(one);await jobs.failJob(one,'failed');await jobs.cancelJobForUser(two,'quota-student');
 expect(await quota()).toMatchObject({used:0,reserved:1,remaining:2});
 await jobs.createJob(args());await jobs.createJob(args());
 await expect(jobs.createJob(args())).rejects.toMatchObject({status:429});
 expect(await jobs.completeJob(two,two)).toBe(false);expect((await jobs.getJob(three)).status).toBe('pending');
});
it('returns the same accepted request even at the limit and never double-counts racing retries',async()=>{
 await completed();await completed();
 const ids=await Promise.all(Array.from({length:5},()=>jobs.createJob(args('quota-student','same-request'))));
 expect(new Set(ids).size).toBe(1);expect(await quota()).toMatchObject({used:2,reserved:1,remaining:0});
 expect(await jobs.createJob(args('quota-student','same-request'))).toBe(ids[0]);
});
it('isolates ordinary users and exempts both administrator roles',async()=>{
 for(let n=0;n<3;n++)await completed();
 expect(await quota('quota-supervisor')).toMatchObject({limited:true,remaining:3});
 await jobs.createJob(args('quota-supervisor'));
 for(const user of ['quota-admin','quota-college']){
  for(let n=0;n<5;n++)await completed(user);
  expect(await quota(user)).toMatchObject({limited:false,remaining:null});
 }
});
it('resets at Shanghai midnight independently of UTC dates and retains old-day task attribution',async()=>{
 vi.setSystemTime(new Date('2026-11-12T15:59:59.900Z'));
 await completed();await completed();const oldPending=await jobs.createJob(args());
 expect(await quota()).toMatchObject({used:2,reserved:1,remaining:0,resets_at:'2026-11-12T16:00:00.000Z'});
 vi.setSystemTime(new Date('2026-11-12T16:00:00.000Z'));
 expect(await quota()).toMatchObject({used:0,reserved:0,remaining:3,resets_at:'2026-11-13T16:00:00.000Z'});
 await jobs.claimJob(oldPending);
 await reports.createPaperLintReport({userId:'quota-student',sourceFilename:'论文.pdf',pdfBuffer:pdf,selectedRuleIds:[],reportId:oldPending,result:{type:'paper_lint',rule_runs:[],summary:{}}});
 await jobs.completeJob(oldPending,oldPending);
 expect((await quota()).remaining).toBe(3);
});
it('does not refund deleted reports and survives reopening the database',async()=>{
 const id=await completed();await completed();await completed();await reports.deletePaperLintReportForUser(id,'quota-student');
 await require('../src/database/init_db').closeDb();
 expect(await quota()).toMatchObject({used:3,remaining:0});
 await expect(jobs.createJob(args())).rejects.toMatchObject({status:429});
});
it('authenticates the quota endpoint and enforces the same admission guard for HTTP submissions',async()=>{
 const {createReviewPilotPaperLintRouter}=require('../src/normative/reviewPilotPaperLintRoutes');
 const {createUserSession}=require('../src/auth/sessionService');
 const session=await createUserSession(await get("SELECT * FROM auth_users WHERE id='quota-student'"));const cookie='arc_session='+session.sessionId;
 const engine={MAX_PDF_BYTES:50*1024*1024,validatePdf:()=>{},normalizeSelectedRuleIds:async ids=>ids};
 const service={enqueue:async input=>{const id=await jobs.createJob(input);return jobs.getJobForUser(id,input.userId);}};
 const app=express();app.use('/api/normative/paper-lint',createReviewPilotPaperLintRouter(engine,{},service,{}));
 await request(app).get('/api/normative/paper-lint/quota').expect(401);
 await request(app).get('/api/normative/paper-lint/quota').set('Cookie',cookie).expect(200).expect(({body})=>expect(body).toMatchObject({remaining:3,limit:3}));
 const submit=()=>request(app).post('/api/normative/paper-lint/run').set('Cookie',cookie).set('Content-Type','application/pdf').set('X-Paper-Lint-Rule-Ids','sjtu_rule_22').send(pdf);
 for(let n=0;n<3;n++)await submit().expect(202);
 await submit().expect(429).expect(({body})=>expect(body.quota).toMatchObject({remaining:0,reserved:3}));
});
it('applies the same daily allowance to incremental reruns without changing the source report',async()=>{
 const id=await completed();await completed();await completed();
 const {createPaperLintJobService}=require('../src/normative/paperLintJobService');
 const engine={validatePdf:vi.fn(),normalizeSelectedRuleIds:async ids=>ids,runPaperLint:vi.fn()};
 const before=await get('SELECT result_json FROM paper_lint_reports WHERE id=?',[id]);
 await expect(createPaperLintJobService(engine).enqueueIncremental({userId:'quota-student',reportId:id,selectedRuleIds:['sjtu_rule_22']})).rejects.toMatchObject({status:429});
 expect(engine.runPaperLint).not.toHaveBeenCalled();expect(await get('SELECT result_json FROM paper_lint_reports WHERE id=?',[id])).toEqual(before);
});
