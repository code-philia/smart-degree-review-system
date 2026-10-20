import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import express from 'express';
import request from 'supertest';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const reportRepository = require('../src/normative/paperLintReportRepository');
const {
  getPaperLintReportFinding,
  findLatestPaperLintRepairSuggestion,
  findPaperLintRepairSuggestion,
  savePaperLintRepairSuggestion,
} = require('../src/normative/paperLintRepairSuggestionService');
const { buildPaperLintReportRepairRequest } = require('../src/normative/legacyRepairAdapter');
const { createPaperLintRepairSuggestionRouter } = require('../src/normative/paperLintRepairSuggestionRoutes');

const harness = createTestDatabaseHarness({ label: 'paper-lint-repair-suggestion' });
let reportsDirectory;
let previousReportsDirectory;
const app = express();
app.use('/api/normative/paper-lint', createPaperLintRepairSuggestionRouter());

function result() {
  return {
    rule_runs: [{
      rule_id: 'sjtu_rule_15',
      findings: [{
        finding_id: 'finding-15-1',
        message: '图 2.3 未被全文引用',
        location: { type: 'pdf_bbox', page_number: 12, text_excerpt: '图 2.3 实验流程', bounding_rect: { page_number: 12 } },
      }],
    }],
  };
}

beforeEach(async () => {
  previousReportsDirectory = process.env.PAPER_LINT_REPORTS_DIR;
  reportsDirectory = path.join(process.cwd(), `.arc-test-paper-lint-repair-reports-${process.pid}-${Date.now()}`);
  process.env.PAPER_LINT_REPORTS_DIR = reportsDirectory;
  const db = await harness.setup();
  await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('owner', 'owner', 'hash', 'STUDENT', 'COLLEGE')");
  await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('other', 'other', 'hash', 'STUDENT', 'COLLEGE')");
  await db.run("INSERT INTO auth_sessions (id, user_id, expires_at) VALUES ('owner-session', 'owner', '2099-01-01T00:00:00.000Z')");
  await db.run("INSERT INTO auth_sessions (id, user_id, expires_at) VALUES ('other-session', 'other', '2099-01-01T00:00:00.000Z')");
  await reportRepository.createPaperLintReport({
    userId: 'owner', sourceFilename: 'paper.pdf', pdfBuffer: Buffer.from('%PDF-1.7'),
    selectedRuleIds: ['sjtu_rule_15'], result: result(), reportId: 'report-1',
  });
});

afterEach(async () => {
  await harness.cleanup();
  await fs.rm(reportsDirectory, { recursive: true, force: true });
  if (previousReportsDirectory === undefined) delete process.env.PAPER_LINT_REPORTS_DIR;
  else process.env.PAPER_LINT_REPORTS_DIR = previousReportsDirectory;
});

describe('single-report repair suggestions', () => {
  it('binds the request and its cache to an owner-scoped report finding', async () => {
    const values = { reportId: 'report-1', userId: 'owner', ruleId: 'sjtu_rule_15', findingId: 'finding-15-1' };
    const { report, ruleRun, finding } = await getPaperLintReportFinding(values);
    const request = buildPaperLintReportRepairRequest({
      report, ruleRun, finding, documentSha256: 'a'.repeat(64),
    });
    expect(request.source).toMatchObject({ kind: 'paper_lint_report', report_id: 'report-1' });
    expect(request.evidence[0]).toMatchObject({ source_ref: 'paper_lint_report:finding_location' });

    const response = {
      schema_version: 'repair-response-v2', source: request.source,
      rule_id: 'sjtu_rule_15', finding_id: 'finding-15-1', status: 'suggested',
      actions: [{ instruction: '在正文补充对图 2.3 的引用。', evidence_ids: ['legacy-evidence-1'] }],
      provenance: {
        provider: 'huawei_maas', model: 'test-model', model_version: 'test-v1', prompt_version: 'prompt-v1',
        context_sha256: request.context_sha256, generated_at: '2026-10-20T00:00:00.000Z',
      },
      usage: { input_tokens: 1, output_tokens: 1, attempts: 1 },
    };
    await savePaperLintRepairSuggestion(request, 'owner', response);
    await savePaperLintRepairSuggestion(request, 'owner', { ...response, actions: [{ instruction: '核对后补充图 2.3 的正文引用。', evidence_ids: ['legacy-evidence-1'] }] });
    await expect(findPaperLintRepairSuggestion(request, {
      model: 'test-model', modelVersion: 'test-v1', promptVersion: 'prompt-v1',
    })).resolves.toMatchObject({ actions: [{ instruction: '核对后补充图 2.3 的正文引用。' }] });
    await expect(findLatestPaperLintRepairSuggestion({
      reportId: 'report-1', userId: 'owner', ruleId: 'sjtu_rule_15', findingId: 'finding-15-1',
    })).resolves.toMatchObject({ actions: [{ instruction: '核对后补充图 2.3 的正文引用。' }] });
  });

  it('does not expose a report finding to a different user', async () => {
    await expect(getPaperLintReportFinding({
      reportId: 'report-1', userId: 'other', ruleId: 'sjtu_rule_15', findingId: 'finding-15-1',
    })).rejects.toMatchObject({ status: 404 });
  });

  it('rejects unsupported rules before a model request can be built', async () => {
    await expect(getPaperLintReportFinding({
      reportId: 'report-1', userId: 'owner', ruleId: 'sjtu_rule_2', findingId: 'anything',
    })).rejects.toMatchObject({ status: 422 });
  });

  it('serves a saved suggestion only to the report owner without re-extracting the PDF', async () => {
    const { report, ruleRun, finding } = await getPaperLintReportFinding({
      reportId: 'report-1', userId: 'owner', ruleId: 'sjtu_rule_15', findingId: 'finding-15-1',
    });
    const repairRequest = buildPaperLintReportRepairRequest({
      report, ruleRun, finding, documentSha256: 'a'.repeat(64),
    });
    const response = {
      schema_version: 'repair-response-v2', source: repairRequest.source,
      rule_id: 'sjtu_rule_15', finding_id: 'finding-15-1', status: 'suggested',
      actions: [{ instruction: '补充图 2.3 的正文引用。', evidence_ids: ['legacy-evidence-1'] }],
      provenance: {
        provider: 'huawei_maas', model: 'test-model', model_version: 'test-v1', prompt_version: 'prompt-v1',
        context_sha256: repairRequest.context_sha256, generated_at: '2026-10-20T00:00:00.000Z',
      },
      usage: { input_tokens: 1, output_tokens: 1, attempts: 1 },
    };
    await savePaperLintRepairSuggestion(repairRequest, 'owner', response);
    await request(app)
      .get('/api/normative/paper-lint/reports/report-1/repair-suggestions?rule_id=sjtu_rule_15&finding_id=finding-15-1')
      .set('Cookie', 'arc_session=owner-session')
      .expect(200)
      .expect(({ body }) => expect(body.response.actions[0].instruction).toBe('补充图 2.3 的正文引用。'));
    await request(app)
      .get('/api/normative/paper-lint/reports/report-1/repair-suggestions?rule_id=sjtu_rule_15&finding_id=finding-15-1')
      .set('Cookie', 'arc_session=other-session')
      .expect(404);
  });
});
