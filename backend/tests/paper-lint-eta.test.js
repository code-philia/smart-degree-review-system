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
    VALUES (?,'student01','eta.pdf','unused',?,?,?,?,?)`,[id,JSON.stringify(Array.isArray(rule)?rule:[rule]),status,new Date(time).toISOString(),new Date(time).toISOString(),started]);
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
it('keeps recalculating a positive numeric ETA after the historical window is exceeded',async()=>{
  await history();await row('running','running',new Date(time-50_000).toISOString());
  expect((await jobs.getJobForUser('running','student01')).eta).toMatchObject({status:'available',max_seconds:175,remaining_seconds:70});
  vi.setSystemTime(time+600_000);
  const late=(await jobs.getJobForUser('running','student01')).eta;
  expect(late.status).toBe('available');expect(late.remaining_seconds).toBeGreaterThan(0);
  vi.setSystemTime(time+720_000);
  const later=(await jobs.getJobForUser('running','student01')).eta;
  expect(later.status).toBe('available');expect(later.remaining_seconds).not.toBe(late.remaining_seconds);
});
it('uses observed rule progress when there is no comparable task history',async()=>{
  const ids=['sjtu_rule_18','sjtu_rule_22','sjtu_rule_24','sjtu_rule_28'];
  await row('progress','running',new Date(time-120_000).toISOString(),ids);
  await jobs.updateProgress('progress',{completed_rule_ids:ids.slice(0,2),total_rule_ids:ids});
  const first=(await jobs.getJobForUser('progress','student01')).eta;
  expect(first).toMatchObject({status:'available',sample_count:0,remaining_seconds:120});
  vi.setSystemTime(time+60_000);
  await jobs.updateProgress('progress',{completed_rule_ids:ids.slice(0,3),total_rule_ids:ids});
  const next=(await jobs.getJobForUser('progress','student01')).eta;
  expect(next).toMatchObject({status:'available',remaining_seconds:60});
  await jobs.updateProgress('progress',{completed_rule_ids:ids,total_rule_ids:ids});
  const saving=(await jobs.getJobForUser('progress','student01')).eta;
  expect(saving.status).toBe('available');expect(saving.remaining_seconds).toBeGreaterThan(0);
});
it('keeps queue estimates numeric when a running job ahead exceeds its initial estimate',async()=>{
  await history();await row('slow','running',new Date(time-650_000).toISOString());await row('waiting');
  const state=(await jobs.getJobForUser('waiting','student01')).eta;
  expect(state.status).toBe('available');expect(state.remaining_seconds).toBeGreaterThan(120);
});
it('does not treat duplicate or unrelated progress IDs as completed selected work',async()=>{
  await row('invalid-progress','running',new Date(time-120_000).toISOString(),['sjtu_rule_18','sjtu_rule_22']);
  await jobs.updateProgress('invalid-progress',{completed_rule_ids:['unselected','unselected'],total_rule_ids:['unselected']});
  expect((await jobs.getJobForUser('invalid-progress','student01')).eta.status).toBe('estimating');
});
it('returns no remaining-time estimate for a completed task',async()=>{
  await history();expect((await jobs.getJobForUser('history-0','student01')).eta).toBeNull();
});
it('clears progress from a previous attempt before estimating a recovered task',async()=>{
  await history();await row('restart','running',new Date(time-100_000).toISOString());
  await jobs.updateProgress('restart',{completed_rule_ids:['sjtu_rule_18'],total_rule_ids:['sjtu_rule_18']});
  await jobs.recoverJobs();await jobs.claimJob('restart');
  const state=await jobs.getJobForUser('restart','student01');
  expect(state.progress).toBeNull();
  expect(state.eta).toMatchObject({status:'available',remaining_seconds:120});
});
