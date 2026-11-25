import express from 'express';
import request from 'supertest';
import { beforeAll, beforeEach, afterAll, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database');
const { run, get } = require('../src/database/db_runtime');
const repository = require('../src/normative/paperLintJobRepository');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const authRoutes = require('../src/auth/authRoutes');
const originalJobs = process.env.PAPER_LINT_JOBS_DIR;
let harness, directory, app;
const cookies = {};
const pdf = Buffer.from('%PDF-1.7\naccount concurrency fixture');
const payload = (userId, requestId = Math.random().toString()) => ({ userId, requestId, sourceFilename: 'paper.pdf', pdfBuffer: pdf, selectedRuleIds: ['sjtu_rule_18'], externalProcessingConsent: false });

beforeAll(async () => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), 'account-activity-test-'));
  process.env.PAPER_LINT_JOBS_DIR = directory;
  harness = createTestDatabaseHarness({ label: 'account-activity', seedDefault: true }); await harness.setup();
  for (const name of ['ordinary-a', 'ordinary-b', 'other-admin']) {
    await run(`INSERT INTO auth_users (id,username,password_hash,role,college_id,supervisor_id,scope)
      SELECT ?,?,password_hash,?,college_id,supervisor_id,scope FROM auth_users WHERE id='student01'`, [name, name, name === 'other-admin' ? 'SCHOOL_ADMIN' : 'STUDENT']);
  }
  const service = { MAX_PDF_BYTES: 50 * 1024 * 1024, validatePdf: vi.fn(), normalizeSelectedRuleIds: async ids => ids };
  const jobs = { enqueue: async values => repository.getJobForUser(await repository.createJob(values), values.userId), getForUser: repository.getJobForUser };
  app = express(); app.use('/api/auth', express.json(), authRoutes);
  app.use('/api/normative/paper-lint', createReviewPilotPaperLintRouter(service, undefined, jobs));
  for (const name of ['ordinary-a', 'ordinary-b', 'other-admin', 'student01', 'supervisor01', 'college_admin01', 'school_admin01']) {
    const response = await request(app).post('/api/auth/login').send({ username: name, password: 'ArcDemo123!' }).expect(200);
    cookies[name] = response.headers['set-cookie'].find(value => value.startsWith('arc_session='));
  }
});
beforeEach(async () => { await run('DELETE FROM paper_lint_jobs'); await run('DELETE FROM paper_lint_upload_leases'); await run('DELETE FROM paper_lint_observed_uploads'); });
afterAll(async () => { await harness.cleanup(); fs.rmSync(directory, { recursive: true, force: true }); if (originalJobs === undefined) delete process.env.PAPER_LINT_JOBS_DIR; else process.env.PAPER_LINT_JOBS_DIR = originalJobs; });

it('admits exactly one unfinished paper even when ordinary-account submissions race', async () => {
  const results = await Promise.allSettled([repository.createJob(payload('ordinary-a')), repository.createJob(payload('ordinary-a'))]);
  expect(results.filter(value => value.status === 'fulfilled')).toHaveLength(1);
  expect(results.find(value => value.status === 'rejected').reason).toMatchObject({ status: 409, code: 'PAPER_LINT_ACTIVE_TASK' });
  expect((await get("SELECT count(*) count FROM paper_lint_jobs WHERE user_id='ordinary-a'")).count).toBe(1);
});
it.each(['student01', 'supervisor01', 'college_admin01', 'school_admin01'])('exempts only the persisted local identity %s', async name => {
  expect((await Promise.all([repository.createJob(payload(name)), repository.createJob(payload(name))])).length).toBe(2);
});
it('does not exempt another administrator or caller-supplied flags', async () => {
  await repository.createJob(payload('other-admin'));
  await expect(repository.createJob({ ...payload('other-admin'), unlimited: true, username: 'school_admin01' })).rejects.toMatchObject({ status: 409 });
});
it('lets different ordinary accounts each own one unfinished task', async () => {
  const ids = await Promise.all([repository.createJob(payload('ordinary-a')), repository.createJob(payload('ordinary-b'))]);
  expect(new Set(ids).size).toBe(2);
});
it.each(['completed', 'failed'])('releases the account slot after a %s task', async status => {
  const id = await repository.createJob(payload('ordinary-a'));
  await run('UPDATE paper_lint_jobs SET status=? WHERE id=?', [status, id]);
  await expect(repository.createJob(payload('ordinary-a'))).resolves.toBeTruthy();
});
it('retries the same request without creating or rejecting a duplicate task', async () => {
  const values = payload('ordinary-a', 'same-request'); const id = await repository.createJob(values);
  await expect(repository.createJob(values)).resolves.toBe(id);
});
it('returns the signed-in account active task so any browser can restore its progress', async () => {
  const id = await repository.createJob(payload('ordinary-a'));
  const state = await request(app).get('/api/normative/paper-lint/activity').set('Cookie', cookies['ordinary-a']).expect(200);
  expect(state.body).toMatchObject({ limited: true, busy: true, uploading: false, active_job: { job_id: id, source_filename: 'paper.pdf' } });
  const other = await request(app).get('/api/normative/paper-lint/activity').set('Cookie', cookies['ordinary-b']).expect(200);
  expect(other.body).toMatchObject({ busy: false, active_job: null });
  await request(app).get('/api/normative/paper-lint/activity').expect(401);
});
it.each(['student01', 'supervisor01', 'college_admin01', 'school_admin01'])('reports %s activity to the UI while preserving unrestricted backend admission', async name => {
  const first = await repository.createJob(payload(name));
  const state = await request(app).get('/api/normative/paper-lint/activity').set('Cookie', cookies[name]).expect(200);
  expect(state.body).toMatchObject({ user_id: name, limited: false, busy: true, active_job: { job_id: first, user_id: name } });
  await expect(repository.createJob(payload(name))).resolves.toBeTruthy();
});
it('rejects a new upload for an occupied ordinary account before parsing its PDF body', async () => {
  await repository.createJob(payload('ordinary-a'));
  const response = await request(app).post('/api/normative/paper-lint/run').set('Cookie', cookies['ordinary-a'])
    .set('Content-Type', 'application/pdf').set('Content-Encoding', 'gzip').set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_18').send(Buffer.from('invalid gzip'));
  expect(response.status).toBe(409); expect(response.body.error_code).toBe('PAPER_LINT_ACTIVE_TASK');
});

it('holds one upload reservation across independent clients and lets only its owner enqueue', async () => {
  const activity = require('../src/normative/paperLintAccountActivity');
  const first = await activity.acquireUpload('ordinary-a', 'upload-a', 'first.pdf');
  await expect(activity.acquireUpload('ordinary-a', 'upload-b', 'second.pdf')).rejects.toMatchObject({ status: 409 });
  await expect(repository.createJob(payload('ordinary-a'))).rejects.toMatchObject({ status: 409 });
  expect(await activity.getAccountActivity('ordinary-a')).toMatchObject({ uploading: true, source_filename: 'first.pdf' });
  await expect(repository.createJob({ ...payload('ordinary-a'), uploadToken: first.token })).resolves.toBeTruthy();
  await activity.releaseUpload('ordinary-a', first.token);
});
it('exposes local uploads to the UI without restricting concurrent backend uploads or jobs', async () => {
  const activity = require('../src/normative/paperLintAccountActivity');
  const first = await activity.acquireUpload('student01', 'local-a', 'first.pdf');
  expect(await activity.getAccountActivity('student01')).toMatchObject({ limited: false, busy: true, uploading: true, source_filename: 'first.pdf' });
  const second = await activity.acquireUpload('student01', 'local-b', 'second.pdf');
  expect(second.token).toBeTruthy(); expect(second.token).not.toBe(first.token);
  await activity.releaseUpload('student01', first.token);
  expect(await activity.getAccountActivity('student01')).toMatchObject({ busy: true, uploading: true, source_filename: 'second.pdf' });
  await expect(repository.createJob(payload('student01'))).resolves.toBeTruthy();
  await expect(repository.createJob(payload('student01'))).resolves.toBeTruthy();
  await activity.releaseUpload('student01', second.token);
});
it('serializes a direct enqueue racing an upload reservation', async () => {
  const activity = require('../src/normative/paperLintAccountActivity');
  const outcomes = await Promise.allSettled([activity.acquireUpload('ordinary-a', 'upload', 'first.pdf'), repository.createJob(payload('ordinary-a'))]);
  expect(outcomes.filter(value => value.status === 'fulfilled')).toHaveLength(1);
});
it('reclaims expired upload reservations and ignores releases from an old owner', async () => {
  const activity = require('../src/normative/paperLintAccountActivity');
  const old = await activity.acquireUpload('ordinary-a', 'old', 'old.pdf');
  await run("UPDATE paper_lint_upload_leases SET expires_at='2000-01-01T00:00:00.000Z' WHERE user_id='ordinary-a'");
  const fresh = await activity.acquireUpload('ordinary-a', 'fresh', 'fresh.pdf');
  await activity.releaseUpload('ordinary-a', old.token);
  expect(await activity.getAccountActivity('ordinary-a')).toMatchObject({ busy: true, uploading: true, source_filename: 'fresh.pdf' });
  await activity.releaseUpload('ordinary-a', fresh.token);
  expect(await activity.getAccountActivity('ordinary-a')).toMatchObject({ busy: false });
});
it('releases an ordinary account upload slot after invalid upload parsing', async () => {
  await request(app).post('/api/normative/paper-lint/run').set('Cookie', cookies['ordinary-a'])
    .set('Content-Type', 'application/pdf').set('Content-Encoding', 'gzip').send(Buffer.from('invalid gzip')).expect(400);
  await expect.poll(async () => (await get("SELECT count(*) count FROM paper_lint_upload_leases WHERE user_id='ordinary-a'")).count).toBe(0);
});
it('recovers an accepted upload with its original request ID without parsing or billing another PDF', async () => {
  const id = await repository.createJob(payload('ordinary-a', 'recovered-id'));
  const response = await request(app).post('/api/normative/paper-lint/run').set('Cookie', cookies['ordinary-a'])
    .set('X-Paper-Lint-Request-Id', 'recovered-id').set('Content-Type', 'application/pdf').set('Content-Encoding', 'gzip').send(Buffer.from('invalid gzip')).expect(202);
  expect(response.body.job_id).toBe(id);
  expect((await get("SELECT count(*) count FROM paper_lint_jobs WHERE user_id='ordinary-a'")).count).toBe(1);
});
it('frees the ordinary account after its pending task is cancelled', async () => {
  const id = await repository.createJob(payload('ordinary-a'));
  await repository.cancelJobForUser(id, 'ordinary-a');
  await expect(repository.createJob(payload('ordinary-a'))).resolves.toBeTruthy();
});
