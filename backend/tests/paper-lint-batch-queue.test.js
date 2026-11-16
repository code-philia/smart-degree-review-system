import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, run, all, get } = require('../src/database');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const repository = require('../src/normative/paperLintJobRepository');
const reports = require('../src/normative/paperLintReportRepository');
const rules = require('../rules/registry').getEnabledMvpRuleIds().filter(id => id !== 'sjtu_rule_32');
const originalEnv = Object.fromEntries(['PAPER_LINT_JOB_CONCURRENCY','REVIEW_PILOT_MAX_CONCURRENT_RUNS','PAPER_LINT_JOBS_DIR','PAPER_LINT_REPORTS_DIR'].map(k => [k,process.env[k]]));
const pdf = Buffer.from('%PDF-1.7\nbatch fixture');
let harness, directory, jobs, engine, releaseAll, gates, active, peak;
function input(requestId) { return { userId: 'batch-admin', sourceFilename: 'thesis.pdf', pdfBuffer: pdf, selectedRuleIds: rules, externalProcessingConsent: true, requestId }; }
beforeEach(async () => {
  directory = await fs.mkdtemp(path.join(os.tmpdir(),'batch-queue-'));
  process.env.PAPER_LINT_JOBS_DIR = path.join(directory,'jobs');
  process.env.PAPER_LINT_REPORTS_DIR = path.join(directory,'reports');
  process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS = '8';
  delete process.env.PAPER_LINT_JOB_CONCURRENCY;
  harness = createTestDatabaseHarness({label:'batch-queue'}); await harness.setup();
  await run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES ('batch-admin','batch-admin','test','SCHOOL_ADMIN','SCHOOL')");
  releaseAll=false;gates=new Map();active=0;peak=0;
  engine={ runPaperLint: vi.fn(async ({runId,selectedRuleIds,signal}) => {
    active++;peak=Math.max(peak,active);
    try {
      if (!releaseAll) await new Promise((resolve,reject) => {
        gates.set(runId,{resolve,reject});
        signal.addEventListener('abort',()=>reject(new Error('aborted')),{once:true});
      });
      expect(selectedRuleIds).toEqual(rules);
      return {selectedRuleIds,result:{type:'paper_lint',rule_runs:[],summary:{finding_count:0}}};
    } finally {active--;gates.delete(runId);}
  })};
});
afterEach(async () => {
  releaseAll=true;for(const gate of gates.values())gate.resolve();
  if(jobs)await jobs.waitForIdle();jobs=null;
  await harness.cleanup();await fs.rm(directory,{recursive:true,force:true});
  for(const [key,value] of Object.entries(originalEnv))if(value===undefined)delete process.env[key];else process.env[key]=value;
});
async function waitCalls(n) {await vi.waitFor(()=>expect(engine.runPaperLint).toHaveBeenCalledTimes(n),{timeout:1800,interval:5});}
async function finish() {releaseAll=true;for(const gate of gates.values())gate.resolve();await jobs.waitForIdle();}

it('runs eight queued papers concurrently and refills a released slot without exceeding eight',async()=>{
  jobs=createPaperLintJobService(engine);
  const submitted=[];for(let i=0;i<12;i++)submitted.push(await jobs.enqueue(input('batch-'+i)));
  await waitCalls(8);expect(active).toBe(8);expect(peak).toBe(8);
  expect((await all("SELECT id FROM paper_lint_jobs WHERE status='pending'")).length).toBe(4);
  gates.get(submitted[3].job_id).resolve();await waitCalls(9);expect(active).toBe(8);expect(peak).toBe(8);
  await finish();expect(peak).toBe(8);
  expect(await reports.listPaperLintReportsByUser('batch-admin')).toHaveLength(12);
  expect(await all("SELECT id FROM paper_lint_jobs WHERE status='completed'")).toHaveLength(12);
});

it.each([['2','99',2],['1','8',1],['8','2',2],['-5','8',1]])('caps requested workers at engine capacity (%s, %s)',async(engineLimit,workers,expected)=>{
  process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS=engineLimit;process.env.PAPER_LINT_JOB_CONCURRENCY=workers;
  jobs=createPaperLintJobService(engine);
  for(let i=0;i<5;i++)await jobs.enqueue(input('limit-'+i));
  await waitCalls(expected);expect(active).toBe(expected);
  await finish();expect(peak).toBe(expected);
});

it('keeps active request retries idempotent and cancellation stops the original execution without email',async()=>{
  process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS='2';jobs=createPaperLintJobService(engine);
  const first=await jobs.enqueue(input('duplicate'));
  expect((await jobs.enqueue(input('duplicate'))).job_id).toBe(first.job_id);
  await jobs.enqueue(input('other'));await waitCalls(2);
  expect((await jobs.enqueue(input('duplicate'))).job_id).toBe(first.job_id);
  const cancelled=await jobs.cancelForUser(first.job_id,'batch-admin');
  expect(cancelled.status).toBe('cancelled');await finish();
  expect(engine.runPaperLint).toHaveBeenCalledTimes(2);
  expect(await reports.findPaperLintReportByIdForUser(first.job_id,'batch-admin')).toBeNull();
  expect(await get('SELECT * FROM report_email_outbox WHERE job_id=?',[first.job_id])).toBeNull();
});

it('continues remaining batch jobs after one detection fails',async()=>{
  process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS='2';jobs=createPaperLintJobService(engine);
  const first=await jobs.enqueue(input('failed'));await jobs.enqueue(input('second'));await jobs.enqueue(input('third'));
  await waitCalls(2);gates.get(first.job_id).reject(new Error('controlled failure'));
  await waitCalls(3);await finish();expect(peak).toBe(2);
  expect((await jobs.getForUser(first.job_id,'batch-admin')).status).toBe('failed');
  expect(await reports.listPaperLintReportsByUser('batch-admin')).toHaveLength(2);
});

it('persists explicit operator batch email suppression without changing the default completion notification',async()=>{
  const quiet=await repository.createJob({...input('silent-batch'),notifyCompletion:false});
  const normal=await repository.createJob(input('normal-default'));
  releaseAll=true;jobs=createPaperLintJobService(engine);await jobs.resumeJobs();await jobs.waitForIdle();
  expect((await get('SELECT notify_completion FROM paper_lint_jobs WHERE id=?',[quiet])).notify_completion).toBe(0);
  expect(await get('SELECT * FROM report_email_outbox WHERE job_id=?',[quiet])).toBeNull();
  expect((await get('SELECT notify_completion FROM paper_lint_jobs WHERE id=?',[normal])).notify_completion).toBe(1);
  expect(await get('SELECT * FROM report_email_outbox WHERE job_id=?',[normal])).toBeTruthy();
  expect(await reports.listPaperLintReportsByUser('batch-admin')).toHaveLength(2);
});
