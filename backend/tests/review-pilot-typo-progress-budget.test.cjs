const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { EventEmitter } = require('node:events');
const { PassThrough } = require('node:stream');
const childProcess = require('node:child_process');
const parentPath = require.resolve('../src/normative/reviewPilotPaperLintService');
const admissionPath = require.resolve('../src/normative/paperDocumentAdmission');
const admissionModule = require(admissionPath);
const localPath = require.resolve('../src/normative/localFiveRulePaperLintService');
const localModule = require(localPath);

async function ready(predicate) {
  for (let i=0; i<500 && !predicate(); i++) await new Promise(resolve => setImmediate(resolve));
  assert.ok(predicate(), 'Controlled semantic worker did not start');
}
function setup(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'typo-budget-'));
  const keys = ['SJTU_API_KEY','SJTU_API_BASE_URL','SJTU_API_MODEL','PAPER_LINT_RUN_TIMEOUT_MS','TMPDIR'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  Object.assign(process.env, { SJTU_API_KEY:'controlled-test-key',SJTU_API_BASE_URL:'https://models.sjtu.edu.cn/api/v1',SJTU_API_MODEL:'controlled',TMPDIR:directory });
  delete process.env.PAPER_LINT_RUN_TIMEOUT_MS;
  const children = [], pending = [];
  const spawn = childProcess.spawn;
  childProcess.spawn = (python, args) => {
    assert.ok(args[0].endsWith('run_bilingual_semantic_lint.py'));
    const child = new EventEmitter();
    child.args = args;
    child.stdout = new PassThrough(); child.stderr = new PassThrough(); child.killed = false;
    child.kill = () => { if (!child.killed) { child.killed=true; queueMicrotask(() => child.emit('close', 1)); } return true; };
    child.finish = () => { child.stdout.write(JSON.stringify({ type:'paper_lint',rule_runs:[{rule_id:'typo_detection_check',execution_status:'completed',outcome:'passed',findings:[]}] })+'\n'); child.emit('close',0); };
    child.work = (count, options={}) => child.stdout.write(JSON.stringify({ type:'paper_lint_chunk_complete',task_id:'private-task',rule_id:'typo_detection_check',execution_status:'completed',chunk_index:count-1,completed_chunks:count,total_chunks:10,...options })+'\n');
    children.push(child); return child;
  };
  require.cache[admissionPath] = { ...require.cache[admissionPath],exports:{ ...admissionModule,assessPaperDocument:async () => ({status:'accepted',stage:'complete',structure:{profile:'chinese-thesis',missing_sections:[],incomplete_sections:[],abstract_sections:{}}}) } };
  require.cache[localPath].exports = { ...localModule,getLocalRuleAvailability:async () => true };
  delete require.cache[parentPath];
  const parent = require(parentPath);
  t.mock.timers.enable({ apis:['setTimeout','Date'] });
  const run = options => { const p=parent.runPaperLint({pdfBuffer:Buffer.from('%PDF-controlled'),selectedRuleIds:['typo_detection_check'],externalProcessingConsent:true,background:true,runId:'private-task',...options}).then(result=>({result}),error=>({error})); pending.push(p); return p; };
  t.after(async () => {
    for (const child of children) child.kill(); await Promise.all(pending); t.mock.timers.reset();
    childProcess.spawn=spawn; require.cache[admissionPath].exports=admissionModule; require.cache[localPath].exports=localModule; delete require.cache[parentPath];
    for (const key of keys) { if (previous[key]===undefined) delete process.env[key]; else process.env[key]=previous[key]; }
    fs.rmSync(directory,{recursive:true,force:true});
  });
  return {run,children};
}

test('trusted operator typo work crosses both old timers and preserves the final rule result', async t => {
  const {run,children}=setup(t); const work=run({trustedBatchProgress:true});
  await ready(()=>children.length===1);
  t.mock.timers.tick(19*60000); children[0].work(1);
  t.mock.timers.tick(2*60000); assert.equal(children[0].killed,false);
  children[0].finish();
  const finished=await work;
  assert.equal(finished.result.result.rule_runs[0].outcome,'passed');
});

test('ordinary background requests cannot extend their deadline using work output', async t => {
  const {run,children}=setup(t); const work=run(); await ready(()=>children.length===1);
  t.mock.timers.tick(19*60000); children[0].work(1);
  t.mock.timers.tick(60001);
  assert.equal((await work).error.code,'PAPER_LINT_TIMEOUT');
});

test('mismatched, failed and duplicate work cannot keep a trusted task alive', async t => {
  const {run,children}=setup(t); const work=run({trustedBatchProgress:true}); await ready(()=>children.length===1);
  t.mock.timers.tick(10*60000); children[0].work(1);
  t.mock.timers.tick(19*60000); children[0].work(1); children[0].work(2,{task_id:'other'}); children[0].work(2,{execution_status:'error'});
  t.mock.timers.tick(60001);
  assert.equal((await work).error.code,'PAPER_LINT_TIMEOUT');
});

test('caller cancellation remains cancellation even after valid chunk work', async t => {
  const {run,children}=setup(t); const controller=new AbortController();
  const work=run({trustedBatchProgress:true,signal:controller.signal}); await ready(()=>children.length===1);
  children[0].work(1); controller.abort(); children[0].work(2);
  assert.equal((await work).error.code,'PAPER_LINT_CANCELLED');
});


test('trusted task with continuing valid work still stops at the absolute cap', async t => {
  const {run,children}=setup(t); const work=run({trustedBatchProgress:true}); await ready(()=>children.length===1);
  for(let n=1;n<=6;n++) { t.mock.timers.tick(19*60000); children[0].work(n); }
  t.mock.timers.tick(6*60000+1);
  assert.equal((await work).error.code,'PAPER_LINT_TIMEOUT');
});

test('an explicit shorter configured deadline also constrains trusted work', async t => {
  const {run,children}=setup(t); process.env.PAPER_LINT_RUN_TIMEOUT_MS='60000';
  const work=run({trustedBatchProgress:true}); await ready(()=>children.length===1);
  t.mock.timers.tick(50000); children[0].work(1); t.mock.timers.tick(10001);
  assert.equal((await work).error.code,'PAPER_LINT_TIMEOUT');
});


test('only private background operator work selects two typo workers', async t => {
  const {run,children}=setup(t); const trusted=run({trustedBatchProgress:true}); await ready(()=>children.length===1);
  const flag=children[0].args.indexOf('--typo-workers');
  assert.ok(flag>=0); assert.equal(children[0].args[flag+1],'2');
  children[0].finish(); assert.ok((await trusted).result);
  const ordinary=run(); await ready(()=>children.length===2);
  assert.equal(children[1].args.includes('--typo-workers'),false);
  children[1].finish(); assert.ok((await ordinary).result);
  const foreground=run({background:false,trustedBatchProgress:true}); await ready(()=>children.length===3);
  assert.equal(children[2].args.includes('--typo-workers'),false);
  children[2].finish(); assert.ok((await foreground).result);
});
