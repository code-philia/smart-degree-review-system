import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database');
const authRoutes = require('../src/auth/authRoutes');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const repository = require('../src/normative/paperLintJobRepository');
const reports = require('../src/normative/paperLintReportRepository');
const pdf = Buffer.from('%PDF-1.7\ncontrolled test');
const result = { type: 'paper_lint', rule_runs: [], summary: { finding_count: 0 }, ruleset: {} };
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
let app, jobs, service, harness, directory;
const cookies = {};

async function submit(ruleId = 'sjtu_rule_22') {
  const response = await request(app).post('/api/normative/paper-lint/run?filename=control.pdf')
    .set('Cookie', cookies.student01).set('Content-Type', 'application/pdf')
    .set('X-Paper-Lint-Rule-Ids', ruleId).send(pdf).expect(202);
  return response.body.job_id;
}
const cancel = (id, name = 'student01') => request(app).post(`/api/normative/paper-lint/jobs/${id}/cancel`).set('Cookie', cookies[name]);

describe('PDF check cancellation and history deletion', () => {
  beforeAll(async () => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), 'paper-lint-controls-'));
    process.env.PAPER_LINT_JOBS_DIR = path.join(directory, 'jobs');
    process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
    harness = createTestDatabaseHarness({ label: 'paper-lint-controls', seedDefault: true });
    await harness.setup();
    service = {
      MAX_PDF_BYTES: 50 * 1024 * 1024,
      validatePdf() {},
      normalizeSelectedRuleIds: async ids => ids,
      runPaperLint: vi.fn(async ({ selectedRuleIds }) => ({ result, selectedRuleIds })),
    };
    jobs = createPaperLintJobService(service);
    app = express();
    app.use('/api/auth', express.json(), authRoutes);
    app.use('/api/normative/paper-lint', createReviewPilotPaperLintRouter(service, undefined, jobs));
    for (const name of ['student01', 'supervisor01']) {
      const login = await request(app).post('/api/auth/login').send({ username: name, password: 'ArcDemo123!' });
      cookies[name] = login.headers['set-cookie'].find(v => v.startsWith('arc_session='));
    }
  });
  afterAll(async () => {
    await harness.cleanup();
    fs.rmSync(directory, { recursive: true, force: true });
    delete process.env.PAPER_LINT_JOBS_DIR;
    delete process.env.PAPER_LINT_REPORTS_DIR;
  });

  it('aborts the owned running detector, rejects another user and never resumes the cancelled job', async () => {
    const entered = deferred();
    let signal, finish;
    service.runPaperLint.mockImplementationOnce(options => new Promise((resolve, reject) => {
      signal = options.signal;
      finish = () => reject(new Error('detector stopped'));
      signal?.addEventListener('abort', finish, { once: true });
      entered.resolve();
    }));
    const id = await submit();
    await entered.promise;
    try {
      await cancel(id, 'supervisor01').expect(404);
      expect(signal?.aborted).not.toBe(true);
      const response = await cancel(id).expect(200);
      expect(response.body.status).toBe('cancelled');
      expect(signal.aborted).toBe(true);
      expect(fs.existsSync(path.join(directory, 'jobs', `${id}.pdf`))).toBe(false);
      await request(app).get(`/api/normative/paper-lint/reports/${id}`).set('Cookie', cookies.student01).expect(404);
      const calls = service.runPaperLint.mock.calls.length;
      await jobs.resumeJobs();
      await jobs.waitForIdle();
      expect(service.runPaperLint.mock.calls.length).toBe(calls);
      expect((await jobs.getForUser(id, 'student01')).status).toBe('cancelled');
    } finally {
      finish();
      await jobs.waitForIdle();
    }
  });

  it('cancels a queued job before its detector starts', async () => {
    const entered = deferred(), release = deferred();
    service.runPaperLint.mockImplementationOnce(async ({ selectedRuleIds }) => {
      entered.resolve(); await release.promise; return { result, selectedRuleIds };
    });
    const before = service.runPaperLint.mock.calls.length;
    await submit();
    await entered.promise;
    const queuedId = await submit();
    try {
      expect((await jobs.getForUser(queuedId, 'student01')).status).toBe('pending');
      expect((await cancel(queuedId).expect(200)).body.status).toBe('cancelled');
    } finally {
      release.resolve(); await jobs.waitForIdle();
    }
    expect(service.runPaperLint.mock.calls.length).toBe(before + 1);
    expect(fs.existsSync(path.join(directory, 'jobs', `${queuedId}.pdf`))).toBe(false);
  });

  it.each(['typo_detection_check', 'bilingual_keywords_correspondence_check', 'bilingual_abstract_consistency_check'])('queues and cancels a standalone %s check', async ruleId => {
    const entered = deferred();
    service.runPaperLint.mockImplementationOnce(({ signal, selectedRuleIds }) => !signal ? Promise.resolve({ result, selectedRuleIds }) : new Promise((resolve, reject) => {
      signal?.addEventListener('abort', () => reject(new Error('cancelled')), { once: true });
      entered.resolve();
    }));
    const id = await submit(ruleId);
    await entered.promise;
    expect((await cancel(id).expect(200)).body.status).toBe('cancelled');
    await jobs.waitForIdle();
  });

  it('removes a late report if cancellation wins during report persistence', async () => {
    const entered = deferred(), release = deferred();
    const realCreate = reports.createPaperLintReport;
    const spy = vi.spyOn(reports, 'createPaperLintReport').mockImplementationOnce(async input => {
      entered.resolve(); await release.promise; return realCreate(input);
    });
    const id = await submit();
    await entered.promise;
    const pending = cancel(id).then(response => response);
    try {
      for (let i = 0; i < 40; i += 1) {
        if ((await jobs.getForUser(id, 'student01')).status === 'cancelled') break;
        await new Promise(resolve => setTimeout(resolve, 5));
      }
      release.resolve();
      expect((await pending).status).toBe(200);
      await jobs.waitForIdle();
      expect(await reports.findPaperLintReportByIdForUser(id, 'student01')).toBeNull();
      expect(fs.existsSync(path.join(directory, 'reports', `${id}.pdf`))).toBe(false);
    } finally {
      release.resolve(); spy.mockRestore(); await jobs.waitForIdle();
    }
  });

  it('deletes an owned report and its PDF without recreating a completed job', async () => {
    const id = await submit();
    await jobs.waitForIdle();
    await request(app).delete(`/api/normative/paper-lint/reports/${id}`).set('Cookie', cookies.supervisor01).expect(404);
    expect(fs.existsSync(path.join(directory, 'reports', `${id}.pdf`))).toBe(true);
    await request(app).delete(`/api/normative/paper-lint/reports/${id}`).set('Cookie', cookies.student01).expect(200);
    expect(await reports.findPaperLintReportByIdForUser(id, 'student01')).toBeNull();
    expect(fs.existsSync(path.join(directory, 'reports', `${id}.pdf`))).toBe(false);
    await jobs.resumeJobs(); await jobs.waitForIdle();
    expect(await reports.findPaperLintReportByIdForUser(id, 'student01')).toBeNull();
  });

  it('validates all batch ownership before deleting any selected reports', async () => {
    const create = userId => reports.createPaperLintReport({ userId, sourceFilename: 'batch.pdf', pdfBuffer: pdf, selectedRuleIds: ['sjtu_rule_22'], result });
    const first = await create('student01'), second = await create('student01'), foreign = await create('supervisor01');
    const remove = ids => request(app).delete('/api/normative/paper-lint/reports').set('Cookie', cookies.student01).send({ report_ids: ids });
    await remove([]).expect(400);
    await remove([first.id, foreign.id]).expect(404);
    expect(await reports.findPaperLintReportByIdForUser(first.id, 'student01')).not.toBeNull();
    const response = await remove([first.id, second.id, first.id]).expect(200);
    expect(response.body.deleted_ids).toEqual(expect.arrayContaining([first.id, second.id]));
    expect(response.body.deleted_ids).toHaveLength(2);
    for (const report of [first, second]) {
      expect(fs.existsSync(path.join(directory, 'reports', `${report.id}.pdf`))).toBe(false);
      expect(await reports.findPaperLintReportByIdForUser(report.id, 'student01')).toBeNull();
    }
    expect(await reports.findPaperLintReportByIdForUser(foreign.id, 'supervisor01')).not.toBeNull();
  });
});
