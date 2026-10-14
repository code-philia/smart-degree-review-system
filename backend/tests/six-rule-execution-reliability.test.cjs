// Only synthetic executables run here; the PDF detector and cloud APIs never run.
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { runSixRules } = require('../src/normative/sixRulePaperLintService');

const ROOT = '/data/results/six-rule-fix-analysis-20261013/service-execution-reliability';
fs.mkdirSync(ROOT, { recursive: true });
const previous = { python: process.env.SIX_RULE_PYTHON, temp: process.env.SIX_RULE_TEMP_DIR };
const folders = [];

function live(pid) {
  try { return fs.readFileSync(`/proc/${pid}/stat`, 'utf8').split(') ').at(-1).split(' ')[0] !== 'Z'; }
  catch { return false; }
}

function fixture(body) {
  const folder = fs.mkdtempSync(path.join(ROOT, 'synthetic-'));
  folders.push(folder);
  const executable = path.join(folder, 'child.cjs');
  const marker = path.join(folder, 'children.json');
  const common = `const fs=require('node:fs');const marker=${JSON.stringify(marker)};`;
  fs.writeFileSync(executable, `#!${process.execPath}\n${common}\n${body}\n`, { mode: 0o700 });
  process.env.SIX_RULE_PYTHON = executable;
  process.env.SIX_RULE_TEMP_DIR = path.join(folder, 'spool');
  return { folder, executable, marker };
}

function validOutput(message = '') {
  const rectangle = { x1: 10, y1: 20, x2: 80, y2: 40, width: 595, height: 842, page_number: 1 };
  return { pages: 1, rules: { 11: { status: 'completed', findings: message ? [{
    message, location: { type: 'pdf_bbox', page_number: 1, bounding_rect: rectangle, rects: [rectangle] },
  }] : [] } } };
}

async function waitFor(predicate, message) {
  const deadline = Date.now() + 2000;
  while (!predicate() && Date.now() < deadline) await new Promise(resolve => setTimeout(resolve, 10));
  assert.ok(predicate(), message);
}

afterEach(() => {
  for (const folder of folders.splice(0)) {
    const marker = path.join(folder, 'children.json');
    if (fs.existsSync(marker)) {
      for (const pid of JSON.parse(fs.readFileSync(marker, 'utf8'))) {
        if (live(pid)) { try { process.kill(pid, 'SIGKILL'); } catch {} }
      }
    }
    fs.rmSync(folder, { recursive: true, force: true });
  }
  for (const [name, value] of [['SIX_RULE_PYTHON', previous.python], ['SIX_RULE_TEMP_DIR', previous.temp]]) {
    if (value === undefined) delete process.env[name]; else process.env[name] = value;
  }
});

test('a valid report larger than 30MiB is returned without losing PDF coordinates', async () => {
  const output = validOutput('placeholder');
  fixture(`const output=${JSON.stringify(output)};output.rules[11].findings[0].message='x'.repeat(31*1024*1024)+'LAST';process.stdout.write(JSON.stringify(output));`);
  const report = await runSixRules('synthetic.pdf', ['sjtu_rule_11']);
  const finding = report.rule_runs[0].findings[0];
  assert.equal(finding.message.length, 31 * 1024 * 1024 + 4);
  assert.ok(finding.message.endsWith('LAST'));
  assert.equal(finding.location.bounding_rect.y1, 20);
}, { timeout: 10000 });

test('more than 30MiB of stderr does not kill a valid detector result', async () => {
  fixture(`process.stderr.write(Buffer.alloc(32*1024*1024,120),()=>process.stdout.write(${JSON.stringify(JSON.stringify(validOutput()))}));`);
  const report = await runSixRules('synthetic.pdf', ['sjtu_rule_11']);
  assert.equal(report.rule_runs[0].outcome, 'passed');
}, { timeout: 10000 });

test('nonzero exit preserves safe code and Python frames without exposing stderr credentials', async () => {
  fixture(`process.stderr.write('Traceback (most recent call last):\\n  File "/data/example/engine.py", line 21, in detect\\nValueError: https://example.invalid/private?signature=SHOULD_NOT_LEAVE_CHILD_STDERR\\nAuthorization: Bearer SHOULD_NOT_LEAVE_CHILD_STDERR\\n');process.exitCode=42;`);
  const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11']).catch(error => error);
  assert.equal(error.status, 502);
  assert.equal(error.code, 'DETECTOR_EXIT_NONZERO');
  assert.equal(error.details.exit_code, 42);
  assert.equal(error.details.stderr_exception_type, 'ValueError');
  assert.deepEqual(error.details.stderr_frames, [{ file: 'engine.py', line: 21, function: 'detect' }]);
  const exposed = JSON.stringify(error) + error.stack;
  assert.ok(!exposed.includes('SHOULD_NOT_LEAVE_CHILD_STDERR'), 'Raw credential-bearing stderr escaped the child boundary');
  assert.ok(!exposed.includes('https://example.invalid'), 'A signed URL escaped the child boundary');
});

test('an externally signalled process is distinct from a timeout', async () => {
  const f = fixture(`fs.writeFileSync(marker,JSON.stringify([process.pid]));setInterval(()=>{},1000);`);
  const pending = runSixRules('synthetic.pdf', ['sjtu_rule_11']).catch(error => error);
  await waitFor(() => fs.existsSync(f.marker), 'Synthetic child did not start');
  process.kill(JSON.parse(fs.readFileSync(f.marker))[0], 'SIGKILL');
  const error = await pending;
  assert.equal(error.code, 'DETECTOR_SIGNALLED');
  assert.equal(error.status, 502);
  assert.equal(error.details.signal, 'SIGKILL');
  assert.equal(error.details.kind, 'process_signal');
});

function resistantTree() {
  return `process.on('SIGTERM',()=>{});const child=require('node:child_process').spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:'ignore'});fs.writeFileSync(marker,JSON.stringify([process.pid,child.pid]));setInterval(()=>{},1000);`;
}

test('timeout escalates TERM to KILL and returns promptly even when the child ignores TERM', async () => {
  const f = fixture(resistantTree());
  const abort = new AbortController();
  const watchdog = setTimeout(() => abort.abort(), 600);
  try {
    const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11'], {
      timeoutMs: 200, killGraceMs: 50, signal: abort.signal,
    }).catch(error => error);
    assert.equal(error.code, 'DETECTOR_TIMEOUT');
    assert.equal(error.details.kind, 'timeout');
    assert.equal(error.status, 504);
    const children = JSON.parse(fs.readFileSync(f.marker));
    await waitFor(() => children.every(pid => !live(pid)), 'Timed out child or grandchild survived');
  } finally { clearTimeout(watchdog); }
}, { timeout: 5000 });

test('caller abort reaps the owned process tree and leaves another process group alive', async () => {
  const f = fixture(resistantTree());
  const unrelated = spawn(process.execPath, ['-e', 'setInterval(()=>{},1000)'], { detached: true, stdio: 'ignore' });
  const abort = new AbortController();
  const pending = runSixRules('synthetic.pdf', ['sjtu_rule_11'], { signal: abort.signal, killGraceMs: 50 }).catch(error => error);
  try {
    await waitFor(() => fs.existsSync(f.marker), 'Synthetic child did not start');
    abort.abort();
    const error = await pending;
    assert.equal(error.name, 'AbortError');
    assert.equal(error.code, 'DETECTOR_ABORTED');
    const children = JSON.parse(fs.readFileSync(f.marker));
    await waitFor(() => children.every(pid => !live(pid)), 'Aborted child or grandchild survived');
    assert.ok(live(unrelated.pid), 'An unrelated process group was killed');
  } finally {
    unrelated.kill('SIGKILL');
    await new Promise(resolve => unrelated.once('close', resolve));
  }
}, { timeout: 5000 });

test('an already aborted signal starts no child', async () => {
  const f = fixture(`fs.writeFileSync(marker,JSON.stringify([process.pid]));process.stdout.write(${JSON.stringify(JSON.stringify(validOutput()))});`);
  const abort = new AbortController(); abort.abort();
  const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11'], { signal: abort.signal }).catch(error => error);
  assert.equal(error.name, 'AbortError');
  assert.equal(error.code, 'DETECTOR_ABORTED');
  assert.ok(!fs.existsSync(f.marker));
});

test('a missing executable remains unavailable with a clear spawn error', async () => {
  const f = fixture(''); process.env.SIX_RULE_PYTHON = path.join(f.folder, 'missing-executable');
  const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11']).catch(error => error);
  assert.equal(error.status, 503);
  assert.equal(error.code, 'DETECTOR_UNAVAILABLE');
  assert.equal(error.details.spawn_code, 'ENOENT');
});

test('invalid stdout is a failure and does not become a passed rule', async () => {
  fixture(`process.stdout.write('not JSON');`);
  const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11']).catch(error => error);
  assert.equal(error.status, 502);
  assert.equal(error.code, 'DETECTOR_INVALID_JSON');
  assert.equal(error.details.stdout_bytes, 8);
});

test('an explicit stdout resource ceiling rejects oversize output instead of returning a partial report', async () => {
  fixture(`const output=${JSON.stringify(validOutput('placeholder'))};output.rules[11].findings[0].message='x'.repeat(4096);process.stdout.write(JSON.stringify(output));`);
  const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11'], {
    maxStdoutBytes: 1024, killGraceMs: 50,
  }).catch(error => error);
  assert.equal(error.code, 'DETECTOR_OUTPUT_LIMIT');
  assert.equal(error.status, 502);
  assert.equal(error.details.max_stdout_bytes, 1024);
  assert.ok(error.details.stdout_bytes > 1024);
});

test('temporary disk failures retain a safe I/O classification and never start a child', async () => {
  const f = fixture(`fs.writeFileSync(marker,JSON.stringify([process.pid]));`);
  const unavailable = path.join(f.folder, 'not-a-directory');
  fs.writeFileSync(unavailable, 'fixture'); process.env.SIX_RULE_TEMP_DIR = unavailable;
  const error = await runSixRules('synthetic.pdf', ['sjtu_rule_11']).catch(error => error);
  assert.equal(error.code, 'DETECTOR_IO_ERROR');
  assert.equal(error.details.io_code, 'EEXIST');
  assert.ok(!fs.existsSync(f.marker));
});

test('successful leader exit also reaps resistant descendants and removes its temporary report', async () => {
  const f = fixture(`const child=require('node:child_process').spawn(process.execPath,['-e',"process.on('SIGTERM',()=>{});setInterval(()=>{},1000)"],{stdio:'ignore'});fs.writeFileSync(marker,JSON.stringify([process.pid,child.pid]));setTimeout(()=>{process.stdout.write(${JSON.stringify(JSON.stringify(validOutput()))},()=>process.exit(0));},150);`);
  const report = await runSixRules('synthetic.pdf', ['sjtu_rule_11'], { killGraceMs: 50 });
  assert.equal(report.rule_runs[0].outcome, 'passed');
  const children = JSON.parse(fs.readFileSync(f.marker));
  await waitFor(() => children.every(pid => !live(pid)), 'A descendant outlived a successful invocation');
  assert.deepEqual(fs.readdirSync(process.env.SIX_RULE_TEMP_DIR), []);
}, { timeout: 5000 });
