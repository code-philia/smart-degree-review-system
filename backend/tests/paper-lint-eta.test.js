import {beforeAll,afterAll,beforeEach,expect,it,vi} from 'vitest';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {createTestDatabaseHarness,run}=require('../src/database');
const jobs=require('../src/normative/paperLintJobRepository');
let harness;const time=Date.parse('2026-11-07T05:00:00Z');
beforeAll(async()=>{harness=createTestDatabaseHarness({label:'eta',seedDefault:true});await harness.setup();});
beforeEach(async()=>{vi.useFakeTimers({toFake:['Date']});vi.setSystemTime(time);await run('DELETE FROM paper_lint_jobs');});
afterAll(async()=>{vi.useRealTimers();await harness.cleanup();});
async function row(id,status='pending',started=null,rule='sjtu_rule_18'){
  await run(`INSERT INTO paper_lint_jobs(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,status,created_at,updated_at,started_at)
    VALUES (?,'student01','eta.pdf','unused',?,?,?,?,?)`,[id,JSON.stringify([rule]),status,new Date(time).toISOString(),new Date(time).toISOString(),started]);
}
async function history(){
  for(const [i,seconds] of [60,120,180].entries()){
    await row('history-'+i,'completed');await run('UPDATE paper_lint_jobs SET started_at=?,created_at=? WHERE id=?',[new Date(time-seconds*1000).toISOString(),new Date(time-seconds*1000).toISOString(),'history-'+i]);
  }
}
it('does not invent an ETA without sufficient comparable history',async()=>{
  await row('new');const state=await jobs.getJobForUser('new','student01');expect(state.eta).toMatchObject({status:'estimating'});
});
it('uses recent task measurements and accounts for jobs ahead in the queue',async()=>{
  await history();await row('first');await row('second');
  const one=await jobs.getJobForUser('first','student01');const two=await jobs.getJobForUser('second','student01');
  expect(one.eta).toMatchObject({status:'available',sample_count:3,min_seconds:48,max_seconds:225,remaining_seconds:120});
  expect(two.eta).toMatchObject({status:'available',min_seconds:96,max_seconds:450,remaining_seconds:240});
});
it('reduces the estimate for elapsed execution and marks an overdue job honestly',async()=>{
  await history();await row('running','running',new Date(time-50_000).toISOString());
  expect((await jobs.getJobForUser('running','student01')).eta).toMatchObject({status:'available',max_seconds:175,remaining_seconds:70});
  vi.setSystemTime(time+600_000);
  expect((await jobs.getJobForUser('running','student01')).eta).toMatchObject({status:'overdue'});
});
it('returns no remaining-time estimate for a completed task',async()=>{
  await history();expect((await jobs.getJobForUser('history-0','student01')).eta).toBeNull();
});
