import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const authRoutes = require('../src/auth/authRoutes');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const paperLintService = require('../src/normative/reviewPilotPaperLintService');
const { createTestDatabaseHarness } = require('../src/database');

const catalog = {
  engine: 'review-pilot',
  mode: 'deterministic',
  rules: [{
    rule_id: 'chinese_title_format_check',
    title: '中文论文题名格式',
    description: '检查中文论文题名页版式。',
    default_severity: 'warning',
    default_enabled: true,
  }],
};

const runResult = {
  type: 'paper_lint',
  paper_title: '测试论文',
  ruleset: { id: 'review-pilot-deterministic', name: 'review-pilot 确定性规则', version_number: 1, version_label: '当前部署版本' },
  rule_runs: [],
  summary: {
    rule_count: 1,
    completed_rule_count: 1,
    unsupported_rule_count: 0,
    error_rule_count: 0,
    issue_rule_count: 0,
    finding_count: 0,
    error_finding_count: 0,
    warning_finding_count: 0,
    info_finding_count: 0,
    derived_rule_count: 1,
  },
};

const fakeService = {
  MAX_PDF_BYTES: paperLintService.MAX_PDF_BYTES,
  getPaperLintCatalog: vi.fn(async () => catalog),
  runPaperLint: vi.fn(async ({ selectedRuleIds }) => ({ result: runResult, selectedRuleIds })),
};

const app = express();
app.use(express.json());
app.use('/api/auth', authRoutes);
app.use('/api/normative/paper-lint', createReviewPilotPaperLintRouter(fakeService));

let harness;
const cookies = {};

describe('review-pilot paper-lint HTTP bridge', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'review-pilot-paper-lint', seedDefault: true });
    await harness.setup();
    for (const username of ['student01', 'supervisor01', 'college_admin01', 'school_admin01']) {
      const login = await request(app)
        .post('/api/auth/login')
        .send({ username, password: 'ArcDemo123!' })
        .expect(200);
      cookies[username] = login.headers['set-cookie'].find((value) => value.startsWith('arc_session='));
    }
  });

  afterAll(async () => harness.cleanup());

  it('denies anonymous access before loading the external engine', async () => {
    fakeService.getPaperLintCatalog.mockClear();
    await request(app).get('/api/normative/paper-lint/rules').expect(401);
    expect(fakeService.getPaperLintCatalog).not.toHaveBeenCalled();
  });

  it('returns the deterministic rule catalog to every declared authenticated role', async () => {
    for (const cookie of Object.values(cookies)) {
      await request(app)
        .get('/api/normative/paper-lint/rules')
        .set('Cookie', cookie)
        .expect(200)
        .expect(catalog);
    }
  });

  it('passes raw PDF bytes and selected rules through without persisting a fake task', async () => {
    const pdf = Buffer.from('%PDF-1.7\nminimal test bytes');
    const response = await request(app)
      .post('/api/normative/paper-lint/run?filename=%E8%AE%BA%E6%96%87.pdf')
      .set('Cookie', cookies.student01)
      .set('Content-Type', 'application/pdf')
      .set('X-Paper-Lint-Rule-Ids', 'chinese_title_format_check')
      .send(pdf)
      .expect(200);

    expect(fakeService.runPaperLint).toHaveBeenCalledWith({
      pdfBuffer: expect.any(Buffer),
      selectedRuleIds: ['chinese_title_format_check'],
    });
    expect(fakeService.runPaperLint.mock.calls.at(-1)[0].pdfBuffer.equals(pdf)).toBe(true);
    expect(response.body).toMatchObject({
      source_filename: '论文.pdf',
      selected_rule_ids: ['chinese_title_format_check'],
      processed_at: expect.any(String),
      result: runResult,
    });
  });
});

describe('review-pilot PDF validation', () => {
  it('accepts a PDF signature and rejects empty or non-PDF input', () => {
    expect(() => paperLintService.validatePdf(Buffer.from('%PDF-1.7\n'))).not.toThrow();
    expect(() => paperLintService.validatePdf(Buffer.alloc(0))).toThrow(/请选择/);
    expect(() => paperLintService.validatePdf(Buffer.from('not a pdf'))).toThrow(/有效的 PDF/);
  });
});
