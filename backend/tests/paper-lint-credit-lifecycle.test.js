import {beforeEach,afterEach,expect,it} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
const require=createRequire(import.meta.url);
const db=require('../src/database');
const {createPaperLintJobService}=require('../src/normative/paperLintJobService');
const credit=require('../src/normative/paperLintCredit');
let harness,dir;
const rule='bilingual_keywords_correspondence_check';
const input=(ids=[rule])=>({userId:'lifecycle',sourceFilename:'paper.pdf',pdfBuffer:Buffer.from('%PDF-1.7\nfixture'),selectedRuleIds:ids,externalProcessingConsent:true});
const checked={selectedRuleIds:[rule],result:{type:'paper_lint',paper_title:'test',rule_runs:[],summary:{finding_count:0}}};
beforeEach(async()=>{
  dir=await fs.mkdtemp(path.join(os.tmpdir(),'credit-lifecycle-'));
  process.env.PAPER_LINT_JOBS_DIR=path.join(dir,'jobs');process.env.PAPER_LINT_REPORTS_DIR=path.join(dir,'reports');
  harness=db.createTestDatabaseHarness({label:'credit-lifecycle'});await harness.setup();
  await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES ('lifecycle','lifecycle','test','STUDENT','COLLEGE')");
});
afterEach(async()=>{await harness.cleanup();await fs.rm(dir,{recursive:true,force:true});delete process.env.PAPER_LINT_JOBS_DIR;delete process.env.PAPER_LINT_REPORTS_DIR;});
it('passes a stored-owner operation only to paid execution and closes it after completion',async()=>{
  let received;
  const service=createPaperLintJobService({runPaperLint:async args=>{received=args;return checked;}});
  const job=await service.enqueue({...input(),creditContext:{operation_id:'attacker',database_file:'/wrong'}});
  await service.waitForIdle();
  expect(received.creditContext).toMatchObject({database_file:db.getDbPath(),operation_id:expect.any(String)});
  expect(received.creditContext.operation_id).not.toBe('attacker');
  expect(await db.get('SELECT * FROM paper_lint_credit_operations WHERE job_id=?',[job.job_id])).toMatchObject({user_id:'lifecycle',state:'closed'});
  expect((await service.getForUser(job.job_id,'lifecycle')).status).toBe('completed');
});
it('does not establish a billing context for an entirely free task',async()=>{
  let received;
  const service=createPaperLintJobService({runPaperLint:async args=>{received=args;return checked;}});
  await service.enqueue(input(['keyword_count_check']));await service.waitForIdle();
  expect(received.creditContext).toBeUndefined();
  expect((await db.get('SELECT count(*) AS n FROM paper_lint_credit_operations')).n).toBe(0);
});
it('closes credit after a cancelled worker has stopped',async()=>{
  let started;const ready=new Promise(resolve=>{started=resolve;});
  const service=createPaperLintJobService({runPaperLint:async args=>new Promise((resolve,reject)=>{
    started();args.signal.addEventListener('abort',()=>reject(new Error('cancelled')),{once:true});
  })});
  const job=await service.enqueue(input());await ready;
  expect((await service.cancelForUser(job.job_id,'lifecycle')).status).toBe('cancelled');
  expect((await db.get('SELECT state FROM paper_lint_credit_operations WHERE job_id=?',[job.job_id])).state).toBe('closed');
  expect((await credit.getAccountCredit('lifecycle')).available_cny).toBe('100.000000000');
});
