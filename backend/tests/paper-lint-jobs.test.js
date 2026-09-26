import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database');
const { run } = require('../src/database/db_runtime');
const authRoutes = require('../src/auth/authRoutes');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const jobRepository = require('../src/normative/paperLintJobRepository');

const pdf = Buffer.from('%PDF-1.7\nsynthetic');
const result = { type: 'paper_lint', paper_title: 'Test',
  ruleset: { id: 'six', name: 'six', version_number: 1, version_label: 'six' },
  rule_runs: [], summary: { rule_count: 1, completed_rule_count: 1, finding_count: 0 } };
let harness;
let directory;
let cookies;
let app;
let jobs;
let service;

describe('durable MinerU paper-lint jobs', () => {
  beforeAll(async () => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), 'paper-lint-jobs-test-'));
    process.env.PAPER_LINT_JOBS_DIR = path.join(directory, 'jobs');
    process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
    harness = createTestDatabaseHarness({ label: 'paper-lint-jobs', seedDefault: true });
    await harness.setup();
    service = {
      MAX_PDF_BYTES: 50 * 1024 * 1024,
      validatePdf: vi.fn(),
      normalizeSelectedRuleIds: vi.fn(async (ids) => ids),
      runPaperLint: vi.fn(async ({ selectedRuleIds }) => ({ result, selectedRuleIds })),
      getPaperLintCatalog: vi.fn(async () => ({ rules: [] })),
    };
    jobs = createPaperLintJobService(service);
    app = express();
    app.use('/api/auth', express.json(), authRoutes);
    app.use('/api/normative/paper-lint', createReviewPilotPaperLintRouter(service, undefined, jobs));
    cookies = {};
    for (const name of ['student01', 'supervisor01']) {
      const login = await request(app).post('/api/auth/login')
        .send({ username: name, password: 'ArcDemo123!' });
      cookies[name] = login.headers['set-cookie'].find((v) => v.startsWith('arc_session='));
    }
  });
  afterAll(async () => {
    await harness.cleanup();
    fs.rmSync(directory, { recursive: true, force: true });
    delete process.env.PAPER_LINT_JOBS_DIR;
    delete process.env.PAPER_LINT_REPORTS_DIR;
  });

  it('returns 202, polls to a single saved report and hides another user job', async () => {
    const submitted = await request(app).post('/api/normative/paper-lint/run?filename=test.pdf')
      .set('Cookie', cookies.student01)
      .set('Content-Type', 'application/pdf')
      .set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_13')
      .send(pdf).expect(202);
    expect(submitted.body.job_id).toBeTruthy();
    expect(submitted.body.status).toMatch(/pending|running|completed/);
    const id = submitted.body.job_id;
    await request(app).get('/api/normative/paper-lint/jobs/' + id)
      .set('Cookie', cookies.supervisor01).expect(404);
    let state;
    for (let i = 0; i < 30; i += 1) {
      state = await request(app).get('/api/normative/paper-lint/jobs/' + id)
        .set('Cookie', cookies.student01).expect(200);
      if (state.body.status === 'completed') break;
      await new Promise((resolve) => setTimeout(resolve, 25));
    }
    expect(state.body.status).toBe('completed');
    expect(state.body.report_id).toBe(id);
    await request(app).get('/api/normative/paper-lint/reports/' + id)
      .set('Cookie', cookies.student01).expect(200);
    expect(fs.existsSync(path.join(directory, 'jobs', id + '.pdf'))).toBe(false);
    expect(service.runPaperLint).toHaveBeenCalledTimes(1);
  });

  it('resumes a persisted running job once and keeps failure visible', async () => {
    service.runPaperLint.mockRejectedValueOnce(new Error('parse failed'));
    const submitted = await request(app).post('/api/normative/paper-lint/run')
      .set('Cookie', cookies.student01).set('Content-Type', 'application/pdf')
      .set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_14').send(pdf).expect(202);
    const id = submitted.body.job_id;
    await jobs.waitForIdle();
    const state = await request(app).get('/api/normative/paper-lint/jobs/' + id)
      .set('Cookie', cookies.student01).expect(200);
    expect(state.body.status).toBe('failed');
    expect(state.body.error_message).toBeTruthy();

    expect(fs.existsSync(path.join(directory, 'jobs', id + '.pdf'))).toBe(false);
    const resumedId = await jobRepository.createJob({
      userId: 'student01', sourceFilename: 'resumed.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_14'], externalProcessingConsent: false,
    });
    await run('UPDATE paper_lint_jobs SET status = ? WHERE id = ?', ['running', resumedId]);
    const restarted = createPaperLintJobService(service);
    await restarted.resumeJobs();
    await restarted.waitForIdle();
    const resumed = await request(app).get('/api/normative/paper-lint/jobs/' + resumedId)
      .set('Cookie', cookies.student01).expect(200);
    expect(resumed.body.status).toBe('completed');
    expect(resumed.body.report_id).toBe(resumedId);
    await restarted.resumeJobs();
    await restarted.waitForIdle();
    expect(service.runPaperLint).toHaveBeenCalledTimes(3);
  });
});
