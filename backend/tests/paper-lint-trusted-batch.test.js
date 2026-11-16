import express from 'express';
import request from 'supertest';
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, run, get, all } = require('../src/database');
const authRoutes = require('../src/auth/authRoutes');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const repository = require('../src/normative/paperLintJobRepository');
const reports = require('../src/normative/paperLintReportRepository');
const realService = require('../src/normative/reviewPilotPaperLintService');
const MiB = 1024 * 1024;
const pdf = Buffer.from('%PDF-1.7\ntrusted original bytes\x00\xff');
const result = { type: 'paper_lint', rule_runs: [], summary: { finding_count: 0 } };
const oldEnv = Object.fromEntries(['PAPER_LINT_JOBS_DIR','PAPER_LINT_REPORTS_DIR','PAPER_LINT_JOB_CONCURRENCY','REVIEW_PILOT_MAX_CONCURRENT_RUNS'].map(k => [k, process.env[k]]));
let directory, harness, app, jobs, engine, gates;
const cookies = {};
function input(overrides = {}) {
  return { userId: 'school_admin01', sourceFilename: 'original.pdf', pdfBuffer: pdf,
    selectedRuleIds: ['sjtu_rule_18'], externalProcessingConsent: true, notifyCompletion: false,
    trustedBatchMaxPdfBytes: 64 * MiB, ...overrides };
}
const start = (id, name = 'school_admin01', body = {}) => request(app)
  .post('/paper-lint/jobs/' + id + '/start').set('Cookie', cookies[name]).send(body);
async function waitCalls(count) {
  await vi.waitFor(() => expect(engine.runPaperLint).toHaveBeenCalledTimes(count), { timeout: 1800, interval: 5 });
}
beforeAll(async () => {
  directory = await fs.mkdtemp(path.join(os.tmpdir(), 'trusted-batch-inputs-'));
  process.env.PAPER_LINT_JOBS_DIR = path.join(directory, 'jobs');
  process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
  process.env.PAPER_LINT_JOB_CONCURRENCY = '1';
  process.env.REVIEW_PILOT_MAX_CONCURRENT_RUNS = '1';
  harness = createTestDatabaseHarness({ label: 'trusted-batch-inputs', seedDefault: true });
  await harness.setup();
  const loginApp = express();
  loginApp.use('/auth', express.json(), authRoutes);
  for (const username of ['school_admin01', 'college_admin01', 'student01', 'supervisor01']) {
    const login = await request(loginApp).post('/auth/login').send({ username, password: 'ArcDemo123!' }).expect(200);
    cookies[username] = login.headers['set-cookie'].find(value => value.startsWith('arc_session='));
  }
});
beforeEach(async () => {
  await run('DELETE FROM report_email_outbox');
  await run('DELETE FROM paper_lint_jobs');
  gates = new Map();
  engine = {
    MAX_PDF_BYTES: realService.MAX_PDF_BYTES,
    validatePdf: realService.validatePdf,
    normalizeSelectedRuleIds: vi.fn(async (ids, consent) => {
      if (!Array.isArray(ids) || !ids.length || ids.some(id => id !== 'sjtu_rule_18')) {
        throw Object.assign(new Error('请选择有效规则'), { status: 400 });
      }
      if (!consent) throw Object.assign(new Error('请确认外部处理'), { status: 400 });
      return ids;
    }),
    runPaperLint: vi.fn(async ({ selectedRuleIds, pdfBuffer, maxPdfBytes }) => {
      realService.validatePdf(pdfBuffer, maxPdfBytes);
      return { result, selectedRuleIds };
    }),
  };
  jobs = createPaperLintJobService(engine);
  app = express();
  app.use('/paper-lint', createReviewPilotPaperLintRouter(engine, undefined, jobs));
});
afterEach(async () => {
  for (const gate of gates.values()) gate();
  await jobs.waitForIdle();
});
afterAll(async () => {
  await harness.cleanup();
  await fs.rm(directory, { recursive: true, force: true });
  for (const [key, value] of Object.entries(oldEnv)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
});

it('keeps the public default at 50 MiB and permits only a bounded internal validator override', async () => {
  const large = Buffer.alloc(50 * MiB + 1); pdf.copy(large);
  expect(() => realService.validatePdf(large)).toThrow(/50/);
  expect(() => realService.validatePdf(large, 64 * MiB)).not.toThrow();
  expect(() => realService.validatePdf(large, 50 * MiB)).toThrow(/50/);
  for (const cap of [49 * MiB, 257 * MiB, Infinity, NaN, '67108864', 64 * MiB + 0.5]) {
    expect(() => realService.validatePdf(pdf, cap)).toThrow();
  }
  const invalid = Buffer.alloc(50 * MiB + 1);
  await expect(realService.runPaperLint({ pdfBuffer: invalid, maxPdfBytes: 64 * MiB, selectedRuleIds: [] }))
    .rejects.toMatchObject({ status: 400, message: '上传内容不是有效的 PDF 文件' });
});

it.each(['student01', 'supervisor01', 'missing-user'])('rejects trusted reservation by actual non-admin DB owner %s before writing', async userId => {
  await expect(repository.createJob(input({ userId }))).rejects.toMatchObject({ status: 403 });
  expect(await all('SELECT id FROM paper_lint_jobs')).toHaveLength(0);
  expect(await fs.readdir(process.env.PAPER_LINT_JOBS_DIR).catch(() => [])).toEqual([]);
});

it('persists the admin cap and original bytes before execution and deduplicates retries', async () => {
  const large = Buffer.alloc(50 * MiB + 1, 0xa7); pdf.copy(large);
  const digest = createHash('sha256').update(large).digest('hex');
  const id = await repository.createJob(input({ pdfBuffer: large, requestId: 'trusted-retry' }));
  expect(await repository.createJob(input({ requestId: 'trusted-retry' }))).toBe(id);
  const row = await repository.getJob(id);
  expect(row.status).toBe('pending');
  expect(row.notify_completion).toBe(0);
  expect(JSON.parse(row.reuse_json)).toEqual({ operator_options: {
    trusted_batch_max_pdf_bytes: 64 * MiB, start_requested: false,
  } });
  expect(createHash('sha256').update(await fs.readFile(row.source_pdf_path)).digest('hex')).toBe(digest);
  expect(engine.runPaperLint).not.toHaveBeenCalled();
  await jobs.resumeJobs(); await jobs.waitForIdle();
  expect(engine.runPaperLint).not.toHaveBeenCalled();
  await start(id).expect(202); await jobs.waitForIdle();
  const saved = await reports.findPaperLintReportByIdForUser(id, 'school_admin01');
  expect(saved.result).toMatchObject(result);
  expect(saved.result.incremental).toBeUndefined();
  expect(engine.runPaperLint.mock.calls[0][0].maxPdfBytes).toBe(64 * MiB);
  const reportPdf = await reports.getPaperLintReportPdfFile(id, 'school_admin01');
  expect(createHash('sha256').update(await fs.readFile(reportPdf.path)).digest('hex')).toBe(digest);
  expect(await get('SELECT * FROM report_email_outbox WHERE job_id=?', [id])).toBeNull();
});

it('rejects over-cap original bytes, invalid signatures and caps above 256 MiB without a pending job', async () => {
  await expect(repository.createJob(input({ trustedBatchMaxPdfBytes: 257 * MiB }))).rejects.toMatchObject({ status: 400 });
  await expect(repository.createJob(input({ pdfBuffer: Buffer.from('not PDF') }))).rejects.toMatchObject({ status: 400 });
  const large = Buffer.alloc(50 * MiB + 1); pdf.copy(large);
  await expect(repository.createJob(input({ pdfBuffer: large, trustedBatchMaxPdfBytes: 50 * MiB })))
    .rejects.toMatchObject({ status: 413 });
  expect(await all('SELECT id FROM paper_lint_jobs')).toHaveLength(0);
});

it('authorizes only an owned trusted reservation and rejects source or limit JSON input', async () => {
  const id = await repository.createJob(input());
  await request(app).post('/paper-lint/jobs/' + id + '/start').send({}).expect(401);
  await start(id, 'student01').expect(403);
  await start(id, 'supervisor01').expect(403);
  await start(id, 'college_admin01').expect(404);
  await start(id, 'school_admin01', { source_pdf_path: '/etc/passwd' }).expect(400);
  await start(id, 'school_admin01', { trustedBatchMaxPdfBytes: 256 * MiB }).expect(400);
  const ordinary = await repository.createJob(input({ trustedBatchMaxPdfBytes: undefined }));
  await start(ordinary).expect(409);
  expect(engine.runPaperLint).not.toHaveBeenCalled();
  const response = await start(id).expect(202);
  expect(response.body.job_id).toBe(id);
  expect(response.body.user_id).toBe('school_admin01');
  await jobs.waitForIdle();
  await start(id).expect(202);
  expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
});

it('accepts both real admin roles and rechecks DB role instead of trusting a stored option', async () => {
  const id = await repository.createJob(input({ userId: 'college_admin01' }));
  await start(id, 'college_admin01').expect(202); await jobs.waitForIdle();
  const revoked = await repository.createJob(input());
  await run("UPDATE auth_users SET role='STUDENT' WHERE id='school_admin01'");
  try {
    await expect(jobs.startTrustedForUser(revoked, 'school_admin01')).rejects.toMatchObject({ status: 403 });
  } finally { await run("UPDATE auth_users SET role='SCHOOL_ADMIN' WHERE id='school_admin01'"); }
});

it.each(['rules', 'consent', 'source'])('revalidates pending %s without queueing or marking started', async mode => {
  const id = await repository.createJob(input(mode === 'rules' ? { selectedRuleIds: [] }
    : mode === 'consent' ? { externalProcessingConsent: false } : {}));
  const row = await repository.getJob(id);
  if (mode === 'source') await fs.rm(row.source_pdf_path);
  await start(id).expect(mode === 'source' ? 410 : 400);
  expect(JSON.parse((await repository.getJob(id)).reuse_json).operator_options.start_requested).toBe(false);
  expect(engine.runPaperLint).not.toHaveBeenCalled();
});

it.each(['pending', 'running'])('restores started %s options after a crash without mistaking the envelope for incremental reuse', async status => {
  const id = await repository.createJob(input());
  const envelope = JSON.parse((await repository.getJob(id)).reuse_json);
  envelope.operator_options.start_requested = true;
  await run("UPDATE paper_lint_jobs SET status=?, reuse_json=? WHERE id=?", [status, JSON.stringify(envelope), id]);
  const restarted = createPaperLintJobService(engine);
  await restarted.resumeJobs(); await restarted.waitForIdle();
  expect((await restarted.getForUser(id, 'school_admin01')).status).toBe('completed');
  expect(engine.runPaperLint.mock.calls[0][0].maxPdfBytes).toBe(64 * MiB);
  expect((await reports.findPaperLintReportByIdForUser(id, 'school_admin01')).result.incremental).toBeUndefined();
});

it('shares the ordinary global worker capacity, starts idempotently, and cancels through the same controller', async () => {
  let active = 0, peak = 0;
  engine.runPaperLint.mockImplementation(({ runId, selectedRuleIds, signal }) => new Promise((resolve, reject) => {
    active++; peak = Math.max(peak, active);
    const finish = () => { active--; gates.delete(runId); resolve({ selectedRuleIds, result }); };
    gates.set(runId, finish);
    signal.addEventListener('abort', () => {
      active--; gates.delete(runId); reject(new Error('cancelled'));
    }, { once: true });
  }));
  const ordinary = await jobs.enqueue(input({ trustedBatchMaxPdfBytes: undefined, requestId: 'normal-worker' }));
  await waitCalls(1);
  const trusted = await repository.createJob(input());
  await start(trusted).expect(202); await start(trusted).expect(202);
  expect(engine.runPaperLint).toHaveBeenCalledTimes(1);
  const metadata = JSON.parse((await repository.getJob(trusted)).reuse_json).operator_options;
  expect(metadata.start_requested).toBe(true);
  await jobs.cancelForUser(ordinary.job_id, 'school_admin01');
  await waitCalls(2);
  await start(trusted).expect(202);
  expect(peak).toBe(1);
  expect((await jobs.cancelForUser(trusted, 'school_admin01')).status).toBe('cancelled');
  await jobs.resumeJobs(); await jobs.waitForIdle();
  expect(engine.runPaperLint).toHaveBeenCalledTimes(2);
  await start(trusted).expect(409);
  expect(await reports.findPaperLintReportByIdForUser(trusted, 'school_admin01')).toBeNull();
});

it('keeps public upload at 50 MiB despite a forged internal cap header or JSON body', async () => {
  const large = Buffer.alloc(50 * MiB + 1); pdf.copy(large);
  await request(app).post('/paper-lint/run?trustedBatchMaxPdfBytes=' + (64 * MiB))
    .set('Cookie', cookies.school_admin01).set('Content-Type', 'application/pdf')
    .set('x-paper-lint-rule-ids', 'sjtu_rule_18')
    .set('x-paper-lint-trusted-batch-max-pdf-bytes', String(64 * MiB)).send(large).expect(413);
  await request(app).post('/paper-lint/run').set('Cookie', cookies.school_admin01)
    .send({ trustedBatchMaxPdfBytes: 64 * MiB, source_pdf_path: '/tmp/large.pdf' }).expect(400);
  expect(await all('SELECT id FROM paper_lint_jobs')).toHaveLength(0);
});

it('rejects a non-JSON start body instead of silently accepting unparsed path input', async () => {
  const id = await repository.createJob(input());
  await request(app).post('/paper-lint/jobs/' + id + '/start').set('Cookie', cookies.school_admin01)
    .set('Content-Type', 'text/plain').send('{"source_pdf_path":"/tmp/large.pdf"}').expect(400);
  expect(JSON.parse((await repository.getJob(id)).reuse_json).operator_options.start_requested).toBe(false);
  expect(engine.runPaperLint).not.toHaveBeenCalled();
});

it('keeps recovering other jobs when an old ordinary reuse payload is corrupt', async () => {
  const broken = await repository.createJob(input({ trustedBatchMaxPdfBytes: undefined }));
  await run('UPDATE paper_lint_jobs SET reuse_json=? WHERE id=?', ['{', broken]);
  const normal = await repository.createJob(input({ trustedBatchMaxPdfBytes: undefined }));
  await expect(jobs.resumeJobs()).resolves.toBeUndefined();
  await jobs.waitForIdle();
  expect((await jobs.getForUser(broken, 'school_admin01')).status).toBe('failed');
  expect((await jobs.getForUser(normal, 'school_admin01')).status).toBe('completed');
});
