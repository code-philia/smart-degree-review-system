// The real parent queue/timer/temp-file code runs; only the PDF engines are
// replaced with controlled promises. No PDF is decoded and no cloud request runs.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ROOT = '/data/results/six-rule-fix-analysis-20261013/service-execution-reliability';
const parentPath = require.resolve('../src/normative/reviewPilotPaperLintService');
const sixPath = require.resolve('../src/normative/sixRulePaperLintService');
const localPath = require.resolve('../src/normative/localFiveRulePaperLintService');
const realSix = require(sixPath);
const realLocal = require(localPath);
const sixModule = require.cache[sixPath];
const localModule = require.cache[localPath];
const rect = { x1: 10, y1: 20, x2: 60, y2: 40, width: 595, height: 842, page_number: 1 };

async function settledIO(predicate) {
  for (let count = 0; count < 1000 && !predicate(); count++) await new Promise(resolve => setImmediate(resolve));
  assert.ok(predicate(), 'Expected synthetic engine/queue transition did not occur');
}

function setup(t, { limit = '2' } = {}) {
  fs.mkdirSync(ROOT, { recursive: true });
  const directory = fs.mkdtempSync(path.join(ROOT, 'parent-budget-'));
  const keys = ['REVIEW_PILOT_BACKEND_DIR', 'REVIEW_PILOT_MAX_CONCURRENT_RUNS', 'PAPER_LINT_RUN_TIMEOUT_MS', 'TMPDIR'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  process.env.REVIEW_PILOT_BACKEND_DIR = path.join(directory, 'unavailable-catalog-engine');
  process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS = limit;
  process.env.TMPDIR = directory;
  delete process.env.PAPER_LINT_RUN_TIMEOUT_MS;
  const calls = [];
  const pending = [];
  function engine(pdfPath, ruleIds, { signal }) {
    assert.ok(pdfPath.startsWith(directory), 'A test temporary PDF escaped the data volume');
    return new Promise((resolve, reject) => {
      const call = { ruleIds, signal, finish: () => {
        signal.removeEventListener('abort', abort);
        resolve({ type: 'paper_lint', rule_runs: ruleIds.map(rule_id => ({ rule_id, outcome: 'issues_found',
          execution_status: 'completed', findings: [{ message: 'synthetic issue', location: { type: 'pdf_bbox', bounding_rect: rect } }] })),
          summary: { finding_count: ruleIds.length } });
      } };
      const abort = () => { const error = new Error('synthetic engine cancelled'); error.status = 504; reject(error); };
      signal.addEventListener('abort', abort, { once: true });
      calls.push(call);
    });
  }
  require.cache[sixPath] = { ...sixModule, exports: { ...realSix, runSixRules: engine } };
  require.cache[localPath] = { ...localModule, exports: { ...realLocal, runLocalFiveRules: engine } };
  delete require.cache[parentPath];
  const parent = require(parentPath);
  t.mock.timers.enable({ apis: ['setTimeout', 'Date'] });
  function run(ids, options = {}) {
    const promise = parent.runPaperLint({ pdfBuffer: Buffer.from('%PDF-synthetic-only'), selectedRuleIds: ids, ...options })
      .then(result => ({ result }), error => ({ error }));
    pending.push(promise);
    return promise;
  }
  t.after(async () => {
    calls.forEach(call => call.finish());
    await Promise.all(pending);
    t.mock.timers.reset();
    require.cache[sixPath] = sixModule;
    require.cache[localPath] = localModule;
    delete require.cache[parentPath];
    for (const key of keys) {
      if (previous[key] === undefined) delete process.env[key]; else process.env[key] = previous[key];
    }
    fs.rmSync(directory, { recursive: true, force: true });
  });
  return { run, calls };
}

test('a foreground six-rule run can finish after five minutes with coordinates intact', async t => {
  const { run, calls } = setup(t);
  const pending = run(['sjtu_rule_11']);
  await settledIO(() => calls.length === 1);
  t.mock.timers.tick(6 * 60 * 1000);
  assert.equal(calls[0].signal.aborted, false);
  calls[0].finish();
  const finished = await pending;
  assert.deepEqual(finished.result.result.rule_runs[0].findings[0].location.bounding_rect, rect);
  assert.deepEqual(finished.result.selectedRuleIds, ['sjtu_rule_11']);
});

test('a foreground legacy-only run still expires at five minutes', async t => {
  const { run, calls } = setup(t);
  const pending = run(['sjtu_rule_18']);
  await settledIO(() => calls.length === 1);
  t.mock.timers.tick(5 * 60 * 1000 + 1);
  assert.equal(calls[0].signal.aborted, true);
  assert.equal((await pending).error.status, 504);
});

test('an explicit shorter foreground six-rule limit is respected', async t => {
  const { run, calls } = setup(t);
  process.env.PAPER_LINT_RUN_TIMEOUT_MS = String(2 * 60 * 1000);
  const pending = run(['sjtu_rule_11']);
  await settledIO(() => calls.length === 1);
  t.mock.timers.tick(2 * 60 * 1000 + 1);
  assert.equal(calls[0].signal.aborted, true);
  assert.equal((await pending).error.status, 504);
});

test('background runs keep their existing twenty-minute window', async t => {
  const { run, calls } = setup(t);
  const pending = run(['sjtu_rule_18'], { background: true });
  await settledIO(() => calls.length === 1);
  t.mock.timers.tick(19 * 60 * 1000);
  assert.equal(calls[0].signal.aborted, false);
  t.mock.timers.tick(60 * 1000 + 1);
  assert.equal(calls[0].signal.aborted, true);
  assert.equal((await pending).error.status, 504);
});

test('six-rule runs still stop at their overall twenty-minute deadline', async t => {
  const { run, calls } = setup(t);
  const pending = run(['sjtu_rule_11']);
  await settledIO(() => calls.length === 1);
  t.mock.timers.tick(19 * 60 * 1000);
  assert.equal(calls[0].signal.aborted, false);
  t.mock.timers.tick(60 * 1000 + 1);
  assert.equal(calls[0].signal.aborted, true);
  assert.equal((await pending).error.status, 504);
});

test('an expired queued run is removed and cannot execute after the previous slot releases', async t => {
  const { run, calls } = setup(t, { limit: '1' });
  const first = run(['sjtu_rule_11']);
  await settledIO(() => calls.length === 1);
  process.env.PAPER_LINT_RUN_TIMEOUT_MS = '1000';
  const expired = run(['sjtu_rule_11']);
  delete process.env.PAPER_LINT_RUN_TIMEOUT_MS;
  const third = run(['sjtu_rule_11']);
  await new Promise(resolve => setImmediate(resolve));
  t.mock.timers.tick(1001);
  assert.equal((await expired).error.status, 504);
  assert.equal(calls.length, 1);
  calls[0].finish(); await first;
  await settledIO(() => calls.length === 2);
  calls[1].finish();
  assert.ok((await third).result);
  assert.equal(calls.length, 2);
});

test('a six-rule request waiting behind a timed-out legacy run retains its larger deadline', async t => {
  const { run, calls } = setup(t, { limit: '1' });
  const first = run(['sjtu_rule_18']);
  await settledIO(() => calls.length === 1);
  const queued = run(['sjtu_rule_11']);
  await new Promise(resolve => setImmediate(resolve));
  t.mock.timers.tick(5 * 60 * 1000 + 1);
  assert.equal((await first).error.status, 504);
  await settledIO(() => calls.length === 2);
  assert.deepEqual(calls[1].ruleIds, ['sjtu_rule_11']);
  assert.equal(calls[1].signal.aborted, false);
  calls[1].finish();
  assert.ok((await queued).result);
});
