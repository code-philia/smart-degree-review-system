import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database');
const authRoutes = require('../src/auth/authRoutes');
const reports = require('../src/normative/paperLintReportRepository');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const metrics = { page_count: 2, word_count: 4, text_available: true, counting_method: 'cjk_characters_and_words' };
const result = { type: 'paper_lint', rule_runs: [], summary: {}, ruleset: {} };
const python = process.env.PAPER_LINT_METRICS_PYTHON || process.env.SIX_RULE_PYTHON || 'python3';
let directory, harness, app, pdfBuffer, owned;
const cookies = {};
const endpoint = id => `/api/normative/paper-lint/reports/${id}/document-metrics`;

describe('owned report document metrics endpoint', () => {
  beforeAll(async () => {
    directory = fs.mkdtempSync(path.join(os.tmpdir(), 'paper-lint-metrics-'));
    process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
    process.env.PAPER_LINT_METRICS_PYTHON = python;
    const pdfPath = path.join(directory, 'fixture.pdf');
    execFileSync(python, ['-c', 'import fitz,sys; d=fitz.open(); p=d.new_page(); p.insert_text((50,50),"Hello world"); p.insert_text((50,100),"中文",fontname="china-s"); d.new_page(); d.save(sys.argv[1])', pdfPath]);
    pdfBuffer = fs.readFileSync(pdfPath);
    harness = createTestDatabaseHarness({ label: 'paper-lint-metrics', seedDefault: true });
    await harness.setup();
    owned = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'fixture.pdf', pdfBuffer, selectedRuleIds: [], result });
    app = express();
    app.use('/api/auth', express.json(), authRoutes);
    app.use('/api/normative/paper-lint', createReviewPilotPaperLintRouter());
    app.use((error, _req, res, _next) => res.status(error.status || 500).json({ message: error.message }));
    for (const name of ['student01', 'supervisor01']) {
      const login = await request(app).post('/api/auth/login').send({ username: name, password: 'ArcDemo123!' });
      cookies[name] = login.headers['set-cookie'].find(value => value.startsWith('arc_session='));
    }
  });

  afterAll(async () => {
    await harness?.cleanup();
    if (directory) fs.rmSync(directory, { recursive: true, force: true });
    delete process.env.PAPER_LINT_REPORTS_DIR;
    delete process.env.PAPER_LINT_METRICS_PYTHON;
  });

  it('requires authentication and rejects foreign or missing reports before extraction', async () => {
    const pdfPath = path.join(directory, 'reports', `${owned.id}.pdf`);
    await request(app).get(endpoint(owned.id)).expect(401);
    await request(app).get(endpoint(owned.id)).set('Cookie', cookies.supervisor01).expect(404);
    await request(app).get(endpoint('missing')).set('Cookie', cookies.student01).expect(404);
    expect(fs.existsSync(`${pdfPath}.metrics.json`)).toBe(false);
  });

  it('extracts full PDF metrics separately without changing the saved result or report payload', async () => {
    const response = await request(app).get(endpoint(owned.id)).set('Cookie', cookies.student01).expect(200);
    expect(response.body).toEqual(metrics);
    const report = await request(app).get(`/api/normative/paper-lint/reports/${owned.id}`).set('Cookie', cookies.student01).expect(200);
    expect(report.body.result).toEqual(result);
    expect(report.body).not.toHaveProperty('document_metrics');
  });

  it('returns 410 for an owned report whose PDF has disappeared', async () => {
    const report = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'gone.pdf', pdfBuffer, selectedRuleIds: [], result });
    fs.rmSync(path.join(directory, 'reports', `${report.id}.pdf`));
    await request(app).get(endpoint(report.id)).set('Cookie', cookies.student01).expect(410);
  });

  it('removes metrics sidecars when the owner deletes reports and preserves foreign reports', async () => {
    const report = await reports.createPaperLintReport({ userId: 'student01', sourceFilename: 'remove.pdf', pdfBuffer, selectedRuleIds: [], result });
    const pdfPath = path.join(directory, 'reports', `${report.id}.pdf`);
    await request(app).get(endpoint(report.id)).set('Cookie', cookies.student01).expect(200);
    expect(fs.existsSync(`${pdfPath}.metrics.json`)).toBe(true);
    await request(app).delete(`/api/normative/paper-lint/reports/${report.id}`).set('Cookie', cookies.supervisor01).expect(404);
    expect(fs.existsSync(`${pdfPath}.metrics.json`)).toBe(true);
    await request(app).delete(`/api/normative/paper-lint/reports/${report.id}`).set('Cookie', cookies.student01).expect(200);
    expect(fs.existsSync(`${pdfPath}.metrics.json`)).toBe(false);
    expect(fs.existsSync(pdfPath)).toBe(false);
  });
});

describe('PDF metrics sidecar cache', () => {
  async function fixture(run) {
    const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'pdf-metrics-cache-'));
    const pdfPath = path.join(temporary, 'source.pdf');
    fs.writeFileSync(pdfPath, 'pdf version one');
    try { await run(pdfPath); }
    finally { fs.rmSync(temporary, { recursive: true, force: true }); }
  }
  const service = options => require('../src/normative/paperLintDocumentMetrics').createDocumentMetricsService(options);

  it('coalesces concurrent requests and reuses a persisted cache across service instances', async () => fixture(async pdfPath => {
    let calls = 0, release;
    const gate = new Promise(resolve => { release = resolve; });
    const current = service({ extractMetrics: async () => { calls += 1; await gate; return metrics; } });
    const first = current.getPaperLintDocumentMetrics(pdfPath);
    const second = current.getPaperLintDocumentMetrics(pdfPath);
    release();
    expect(await Promise.all([first, second])).toEqual([metrics, metrics]);
    expect(calls).toBe(1);
    const fresh = service({ extractMetrics: async () => { throw new Error('cache was missed'); } });
    expect(await fresh.getPaperLintDocumentMetrics(pdfPath)).toEqual(metrics);
  }));

  it('invalidates a sidecar when PDF size, modification time or counting version changes', async () => fixture(async pdfPath => {
    let calls = 0;
    const current = service({ extractMetrics: async () => ({ ...metrics, word_count: ++calls }) });
    expect((await current.getPaperLintDocumentMetrics(pdfPath)).word_count).toBe(1);
    fs.appendFileSync(pdfPath, 'changed');
    expect((await current.getPaperLintDocumentMetrics(pdfPath)).word_count).toBe(2);
    const stat = fs.statSync(pdfPath);
    fs.utimesSync(pdfPath, stat.atime, new Date(stat.mtimeMs + 5000));
    expect((await current.getPaperLintDocumentMetrics(pdfPath)).word_count).toBe(3);
    const cached = JSON.parse(fs.readFileSync(`${pdfPath}.metrics.json`, 'utf8'));
    cached.counting_version = 'obsolete';
    fs.writeFileSync(`${pdfPath}.metrics.json`, JSON.stringify(cached));
    expect((await current.getPaperLintDocumentMetrics(pdfPath)).word_count).toBe(4);
  }));

  it('ignores malformed cached metrics and continues when the sidecar cannot be written', async () => fixture(async pdfPath => {
    fs.mkdirSync(`${pdfPath}.metrics.json`);
    const current = service({ extractMetrics: async () => metrics });
    expect(await current.getPaperLintDocumentMetrics(pdfPath)).toEqual(metrics);
    fs.rmSync(`${pdfPath}.metrics.json`, { recursive: true });
    fs.writeFileSync(`${pdfPath}.metrics.json`, '{broken');
    expect(await current.getPaperLintDocumentMetrics(pdfPath)).toEqual(metrics);
  }));

  it('does not cache extraction failures and permits a successful retry', async () => fixture(async pdfPath => {
    let calls = 0;
    const current = service({ extractMetrics: async () => { if (++calls === 1) throw new Error('unreadable'); return metrics; } });
    await expect(current.getPaperLintDocumentMetrics(pdfPath)).rejects.toThrow('unreadable');
    expect(fs.existsSync(`${pdfPath}.metrics.json`)).toBe(false);
    expect(await current.getPaperLintDocumentMetrics(pdfPath)).toEqual(metrics);
  }));

  it('limits extraction runtime and stdout instead of leaving an unbounded process', async () => fixture(async pdfPath => {
    const hung = path.join(path.dirname(pdfPath), 'hung.py');
    fs.writeFileSync(hung, 'import time\ntime.sleep(30)\n');
    const bounded = service({ python, scriptPath: hung, timeoutMs: 50 });
    await expect(bounded.getPaperLintDocumentMetrics(pdfPath)).rejects.toMatchObject({ status: 503 });
    const noisy = path.join(path.dirname(pdfPath), 'noisy.py');
    fs.writeFileSync(noisy, 'print("x" * 10000)\n');
    await expect(service({ python, scriptPath: noisy, maxOutputBytes: 100 }).getPaperLintDocumentMetrics(pdfPath)).rejects.toMatchObject({ status: 503 });
  }));
});
