import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
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
  beforeEach(async () => {
  // Keep unrelated job/mail cases independent of the daily quota.
  await run("UPDATE paper_lint_jobs SET created_at = ? WHERE status IN ('completed','failed')", [new Date(Date.now() - 86400000).toISOString()]);
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
      .set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_18')
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

  it('previews only the current user pending PDF and continues serving it after completion', async () => {
    const id = await jobRepository.createJob({ userId: 'student01', sourceFilename: 'private.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_18'], externalProcessingConsent: false });
    const url = '/api/normative/paper-lint/jobs/' + id + '/pdf';
    await request(app).get(url).expect(401);
    await request(app).get(url).set('Cookie', cookies.supervisor01).expect(404);
    const preview = await request(app).get(url).set('Cookie', cookies.student01).expect(200);
    expect(preview.headers['content-type']).toContain('application/pdf');
    expect(preview.headers['cache-control']).toContain('private');
    await request(app).get(url).set('Cookie', cookies.student01).set('Range', 'bytes=0-7').expect(206);
    await jobs.resumeJobs();
    await jobs.waitForIdle();
    await request(app).get(url).set('Cookie', cookies.student01).expect(200);
    await request(app).get(url).set('Cookie', cookies.supervisor01).expect(404);
  });

  it('resumes a persisted running job once and keeps failure visible', async () => {
    const callsBefore = service.runPaperLint.mock.calls.length;
    service.runPaperLint.mockRejectedValueOnce(new Error('parse failed'));
    const submitted = await request(app).post('/api/normative/paper-lint/run')
      .set('Cookie', cookies.student01).set('Content-Type', 'application/pdf')
      .set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_22').send(pdf).expect(202);
    const id = submitted.body.job_id;
    await jobs.waitForIdle();
    const state = await request(app).get('/api/normative/paper-lint/jobs/' + id)
      .set('Cookie', cookies.student01).expect(200);
    expect(state.body.status).toBe('failed');
    expect(state.body.error_message).toBeTruthy();

    expect(fs.existsSync(path.join(directory, 'jobs', id + '.pdf'))).toBe(false);
    const resumedId = await jobRepository.createJob({
      userId: 'student01', sourceFilename: 'resumed.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_22'], externalProcessingConsent: false,
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
    expect(service.runPaperLint).toHaveBeenCalledTimes(callsBefore + 2);
  });
  it.each(['sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24', 'sjtu_rule_28'])(
    'runs %s in a durable background job without holding the upload request open', async (ruleId) => {
      const submitted = await request(app).post('/api/normative/paper-lint/run')
        .set('Cookie', cookies.student01).set('Content-Type', 'application/pdf')
        .set('X-Paper-Lint-Rule-Ids', ruleId).send(pdf).expect(202);
      await jobs.waitForIdle();
      const state = await request(app).get('/api/normative/paper-lint/jobs/' + submitted.body.job_id)
        .set('Cookie', cookies.student01).expect(200);
      expect(state.body.status).toBe('completed');
      const report = await request(app).get('/api/normative/paper-lint/reports/' + state.body.report_id)
        .set('Cookie', cookies.student01).expect(200);
      expect(report.body.selected_rule_ids).toEqual([ruleId]);
    });

  it('shows queue position and removes cancelled waiting jobs from the count', async () => {
    let release;
    const waiting = new Promise(resolve => { release = resolve; });
    service.runPaperLint.mockImplementationOnce(async ({ selectedRuleIds }) => {
      await waiting; return { result, selectedRuleIds };
    });
    const submit = () => request(app).post('/api/normative/paper-lint/run')
      .set('Cookie', cookies.student01).set('Content-Type', 'application/pdf')
      .set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_18').send(pdf).expect(202);
    try {
      const first = await submit();
      const second = await submit();
      const third = await submit();
      const position = await request(app).get('/api/normative/paper-lint/jobs/' + third.body.job_id)
        .set('Cookie', cookies.student01).expect(200);
      expect(position.body.status).toBe('pending');
      expect(position.body.queue_position).toBe(3);
      await request(app).post('/api/normative/paper-lint/jobs/' + second.body.job_id + '/cancel')
        .set('Cookie', cookies.student01).expect(200);
      const after = await request(app).get('/api/normative/paper-lint/jobs/' + third.body.job_id)
        .set('Cookie', cookies.student01).expect(200);
      expect(after.body.queue_position).toBe(2);
    } finally { release(); await jobs.waitForIdle(); }
  });

  it('reuses successful findings, retries failures and missing rules, and never uploads a new PDF', async () => {
    const reports = require('../src/normative/paperLintReportRepository');
    const kept = { rule_id: 'sjtu_rule_18', rule_run_id: 'kept', severity: 'warning',
      execution_status: 'completed', outcome: 'issues_found', findings: [{ finding_id: 'old', message: '保留的问题' }] };
    const failed = { ...kept, rule_id: 'sjtu_rule_22', execution_status: 'error', outcome: 'inconclusive', findings: [] };
    const uncertain = { ...failed, rule_id: 'sjtu_rule_24', execution_status: 'completed' };
    const source = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'original.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_18','sjtu_rule_22','sjtu_rule_24'], result: { ...result, rule_runs: [kept,failed,uncertain] } });
    await request(app).post(`/api/normative/paper-lint/reports/${source.id}/rerun`)
      .set('Cookie', cookies.supervisor01).send({ selected_rule_ids: ['sjtu_rule_28'] }).expect(404);
    service.runPaperLint.mockImplementationOnce(async ({ selectedRuleIds, pdfBuffer, onProgress }) => {
      expect(selectedRuleIds).toEqual(['sjtu_rule_22','sjtu_rule_24','sjtu_rule_28']);
      expect(pdfBuffer.equals(pdf)).toBe(true);
      const runs = selectedRuleIds.map(id => ({ ...kept, rule_id: id, findings: [], outcome: 'passed' }));
      await onProgress({ completed_rule_ids: selectedRuleIds, total_rule_ids: selectedRuleIds, rule_runs: runs });
      return { selectedRuleIds, result: { ...result, rule_runs: runs } };
    });
    const rerun = await request(app).post(`/api/normative/paper-lint/reports/${source.id}/rerun`)
      .set('Cookie', cookies.student01).set('X-Paper-Lint-Request-Id', 'rerun-one')
      .send({ selected_rule_ids: ['sjtu_rule_28'] }).expect(202);
    await jobs.waitForIdle();
    const saved = await reports.findPaperLintReportByIdForUser(rerun.body.job_id, 'student01');
    expect(saved.selected_rule_ids).toEqual(['sjtu_rule_18','sjtu_rule_22','sjtu_rule_24','sjtu_rule_28']);
    expect(saved.result.rule_runs[0]).toEqual(kept);
    expect(saved.summary.finding_count).toBe(1);
    expect(saved.result.incremental.reused_rule_ids).toEqual(['sjtu_rule_18']);
    expect((await reports.findPaperLintReportByIdForUser(source.id, 'student01')).result.rule_runs).toHaveLength(3);
    const state = await jobs.getForUser(rerun.body.job_id, 'student01');
    expect(state.progress.completed_rule_ids).toHaveLength(4);
  });

  it('persists reusable results across a restart without depending on the old report', async () => {
    const kept = { rule_id: 'sjtu_rule_18', rule_run_id: 'old', severity: 'warning', execution_status: 'completed', outcome: 'passed', findings: [] };
    const id = await jobRepository.createJob({ userId: 'student01', sourceFilename: 'durable.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_18', 'sjtu_rule_22'], externalProcessingConsent: true,
      reuse: { source_report_id: 'deleted-source', result: { ...result, rule_runs: [kept] } } });
    await run("UPDATE paper_lint_jobs SET status='running' WHERE id=?", [id]);
    service.runPaperLint.mockImplementationOnce(async ({ selectedRuleIds }) => {
      expect(selectedRuleIds).toEqual(['sjtu_rule_22']);
      return { selectedRuleIds, result: { ...result, rule_runs: [{ ...kept, rule_id: 'sjtu_rule_22' }] } };
    });
    const restarted = createPaperLintJobService(service);
    await restarted.resumeJobs(); await restarted.waitForIdle();
    expect((await restarted.getForUser(id, 'student01')).status).toBe('completed');
    const saved = await require('../src/normative/paperLintReportRepository').findPaperLintReportByIdForUser(id, 'student01');
    expect(saved.result.rule_runs.map(run => run.rule_id)).toEqual(['sjtu_rule_18', 'sjtu_rule_22']);
  });

  it('discards old passing rules when document admission rejects an incremental rerun', async () => {
    const kept = { rule_id: 'sjtu_rule_18', rule_run_id: 'old-pass', severity: 'warning', execution_status: 'completed', outcome: 'passed', findings: [] };
    const id = await jobRepository.createJob({ userId: 'student01', sourceFilename: 'form.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_18', 'sjtu_rule_22'], externalProcessingConsent: true,
      reuse: { source_report_id: 'legacy-form', result: { ...result, rule_runs: [kept] } } });
    const rejection = require('../src/normative/paperDocumentAdmission').documentRejectionResult(
      { status: 'rejected', reason_code: 'non_paper_identity', reason: '推荐表' }, ['sjtu_rule_22']);
    service.runPaperLint.mockImplementationOnce(async ({ onProgress }) => {
      await onProgress({ completed_rule_ids: [], rule_runs: rejection.rule_runs, document_validation: rejection.document_validation });
      return { result: rejection, selectedRuleIds: ['sjtu_rule_22'] };
    });
    const restarted = createPaperLintJobService(service);
    await restarted.resumeJobs(); await restarted.waitForIdle();
    const saved = await require('../src/normative/paperLintReportRepository').findPaperLintReportByIdForUser(id, 'student01');
    expect(saved.result.rule_runs.map(run => run.rule_id)).toEqual(['document_type_check']);
    expect(saved.summary.error_finding_count).toBe(1);
    expect(saved.result.document_validation.skipped_rule_ids).toEqual(['sjtu_rule_18', 'sjtu_rule_22']);
    expect(saved.result.incremental.reused_rule_ids).toEqual([]);
    expect((await restarted.getForUser(id, 'student01')).progress.rule_runs.map(run => run.rule_id)).toEqual(['document_type_check']);
  });

  it('rejects a redundant rerun and a missing original PDF without submitting model work', async () => {
    const reports = require('../src/normative/paperLintReportRepository');
    const kept = { rule_id: 'sjtu_rule_18', rule_run_id: 'kept', severity: 'warning', execution_status: 'completed', outcome: 'passed', findings: [] };
    const source = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'missing.pdf', pdfBuffer: pdf,
      selectedRuleIds: ['sjtu_rule_18'], result: { ...result, rule_runs: [kept] } });
    const before = service.runPaperLint.mock.calls.length;
    await request(app).post(`/api/normative/paper-lint/reports/${source.id}/rerun`)
      .set('Cookie', cookies.student01).send({ selected_rule_ids: [] }).expect(400);
    const file = await reports.getPaperLintReportPdfFile(source.id, 'student01');
    fs.unlinkSync(file.path);
    await request(app).post(`/api/normative/paper-lint/reports/${source.id}/rerun`)
      .set('Cookie', cookies.student01).send({ selected_rule_ids: ['sjtu_rule_22'] }).expect(410);
    expect(service.runPaperLint).toHaveBeenCalledTimes(before);
  });

  it.each([false, true])('deduplicates core findings live and saved unless explicitly selected (%s)', async (explicitCore) => {
    const reports = require('../src/normative/paperLintReportRepository');
    const core = { rule_id: 'required_section_completeness_check', rule_run_id: 'background-core', severity: 'warning',
      execution_status: 'completed', outcome: 'issues_found', params: { automatic_core_check: true },
      findings: [{ finding_id: 'missing-cn', rule_id: 'required_section_completeness_check', core_section: '摘要', message: '缺少中文摘要' }] };
    const keyword = { rule_id: 'keyword_count_check', rule_run_id: 'no-keywords', severity: 'info',
      execution_status: 'unsupported', outcome: 'inconclusive', params: { core_structure_sections: ['摘要'] },
      findings: [], message: '缺少中文摘要，无法检查关键词数量' };
    const kept = { rule_id: 'sjtu_rule_31', rule_run_id: 'kept-reference-format', severity: 'warning',
      execution_status: 'completed', outcome: 'passed', findings: [] };
    const selectedIds = ['keyword_count_check', 'sjtu_rule_31', ...(explicitCore ? [core.rule_id] : [])];
    const reusedCore = explicitCore ? { ...core, params: {}, findings: [...core.findings,
      { finding_id: 'missing-declaration', rule_id: core.rule_id, message: '缺少原创性声明' }] } : core;
    const source = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'partial.pdf', pdfBuffer: pdf,
      selectedRuleIds: selectedIds, result: { ...result, rule_runs: [keyword, kept, reusedCore] } });
    service.runPaperLint.mockImplementationOnce(async ({ selectedRuleIds, onProgress }) => {
      await onProgress({ completed_rule_ids: [core.rule_id, keyword.rule_id],
        total_rule_ids: [keyword.rule_id, core.rule_id], rule_runs: [core, keyword] });
      return { selectedRuleIds, result: { ...result, rule_runs: [keyword, core] } };
    });
    const job = await jobs.enqueueIncremental({ userId: 'student01', reportId: source.id, requestId: `mandatory-core-rerun-${explicitCore}` });
    await jobs.waitForIdle();
    const saved = await reports.findPaperLintReportByIdForUser(job.job_id, 'student01');
    expect(saved.selected_rule_ids).toEqual(selectedIds);
    expect(saved.result.rule_runs).toContainEqual(kept);
    const state = await jobs.getForUser(job.job_id, 'student01');
    if (!explicitCore) {
      expect(saved.result.rule_runs.some(run=>run.rule_id===core.rule_id)).toBe(false);
      expect(state.progress.rule_runs.some(run=>run.rule_id===core.rule_id)).toBe(false);
      expect(state.progress.total_rule_ids).not.toContain(core.rule_id);
      return;
    }
    expect(saved.result.rule_runs.find(run => run.rule_id === core.rule_id)).toMatchObject({
      severity: 'error', params: { automatic_core_check: true },
      findings: expect.arrayContaining([expect.objectContaining({ message: '缺少中文摘要' })]) });
    expect(state.progress.total_rule_ids).toContain(core.rule_id);
    expect(state.progress.rule_runs.filter(run => run.rule_id === core.rule_id)).toHaveLength(1);
    const liveMessages = state.progress.rule_runs.find(run => run.rule_id === core.rule_id).findings.map(f => f.message);
    expect(liveMessages).toEqual(saved.result.rule_runs.find(run => run.rule_id === core.rule_id).findings.map(f => f.message));
    expect(liveMessages).toHaveLength(explicitCore ? 2 : 1);
  });


  it('reruns an automatic-only core result when core is newly selected during incremental checking', async () => {
    const reports = require('../src/normative/paperLintReportRepository');
    const coreId = 'required_section_completeness_check';
    const conclusion = { finding_id: 'mandatory_core_结论', core_section: '结论', message: '缺少结论' };
    const abstract = { finding_id: 'native-cn', core_section: '摘要', message: '缺少中文摘要' };
    const automatic = { rule_id: coreId, severity: 'error', execution_status: 'completed',
      outcome: 'issues_found', params: { automatic_core_check: true }, findings: [conclusion] };
    const keyword = { rule_id: 'keyword_count_check', severity: 'info', execution_status: 'unsupported',
      outcome: 'inconclusive', params: { core_structure_sections: ['摘要'] }, findings: [] };
    const source = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'partial-add-core.pdf', pdfBuffer: pdf,
      selectedRuleIds: [keyword.rule_id], result: { ...result, rule_runs: [keyword, automatic] } });
    service.runPaperLint.mockImplementationOnce(async ({ selectedRuleIds, onProgress }) => {
      const runs = [keyword, selectedRuleIds.includes(coreId)
        ? { ...automatic, params: null, findings: [abstract, conclusion] } : automatic];
      await onProgress({ completed_rule_ids: runs.map(r=>r.rule_id), total_rule_ids: selectedRuleIds, rule_runs: runs });
      return { selectedRuleIds, result: { ...result, rule_runs: runs } };
    });
    const job = await jobs.enqueueIncremental({ userId: 'student01', reportId: source.id,
      selectedRuleIds: [coreId], requestId: 'newly-selected-core' });
    await jobs.waitForIdle();
    const saved = await reports.findPaperLintReportByIdForUser(job.job_id, 'student01');
    expect(saved.result.rule_runs.find(r=>r.rule_id===coreId).findings.map(f=>f.message))
      .toEqual(['缺少中文摘要', '缺少结论']);
  });
});
