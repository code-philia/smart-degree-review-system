import { afterAll, beforeAll, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const reports = require('../src/normative/paperLintReportRepository');
const { getPaperLintReportFinding } = require('../src/normative/paperLintRepairSuggestionService');
const { buildPaperLintReportRepairRequest } = require('../src/normative/legacyRepairAdapter');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const { getPaperLintCatalog } = require('../src/normative/reviewPilotPaperLintService');
const rule = 'abstract_numeric_consistency_check';
const harness = createTestDatabaseHarness({ label: 'numeric-review' });
let directory, previousReports, previousJobs;
const loc = { type: 'pdf_page', page_number: 8, text_excerpt: 'Accuracy89.3%' };
const result = {
  type: 'paper_lint', ruleset: { version_label: 'numeric-test' }, summary: { rule_count: 1, finding_count: 1 },
  rule_runs: [{ rule_id: rule, rule_run_id: 'numeric-run', outcome: 'issues_found', execution_status: 'completed',
    params: { trace: { run_id: 'trace-test' }, declarations: [{ id: 'd1' }] },
    findings: [{ finding_id: 'd1', message: '数值不一致', location: loc,
      anchors: [{ anchor_id: 'exp', label: '实验结果证据', location: loc }, { anchor_id: 'abs', label: '摘要数值声明', location: { type: 'pdf_page', page_number: 2 } }],
      evidence: [{ id: 'exp', quote: 'Accuracy89.3%' }, { id: 'abs', quote: '准确率92.5%' }] }],
  }],
};
beforeAll(async () => {
  directory = await fs.mkdtemp(path.join(process.cwd(), '.arc-test-numeric-'));
  previousReports = process.env.PAPER_LINT_REPORTS_DIR;
  previousJobs = process.env.PAPER_LINT_JOBS_DIR;
  process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
  process.env.PAPER_LINT_JOBS_DIR = path.join(directory, 'jobs');
  const db = await harness.setup();
  await db.run("INSERT INTO auth_users (id, username, password_hash, role, scope) VALUES ('numeric-owner','numeric-owner','hash','STUDENT','COLLEGE')");
});
afterAll(async () => {
  await harness.cleanup();
  await fs.rm(directory, { recursive: true, force: true });
  if (previousReports === undefined) delete process.env.PAPER_LINT_REPORTS_DIR;
  else process.env.PAPER_LINT_REPORTS_DIR = previousReports;
  if (previousJobs === undefined) delete process.env.PAPER_LINT_JOBS_DIR;
  else process.env.PAPER_LINT_JOBS_DIR = previousJobs;
});
it('persists numeric results and trace metadata with owner-scoped history', async () => {
  await reports.createPaperLintReport({ userId: 'numeric-owner', sourceFilename: 'numeric.pdf', pdfBuffer: Buffer.from('%PDF-test'), selectedRuleIds: [rule], result, reportId: 'numeric-report' });
  const history = await reports.listPaperLintReportsByUser('numeric-owner');
  expect(history[0].selected_rule_ids).toEqual([rule]);
  const saved = await reports.findPaperLintReportByIdForUser('numeric-report', 'numeric-owner');
  expect(saved.result.rule_runs[0].params.trace.run_id).toBe('trace-test');
  expect(await reports.findPaperLintReportByIdForUser('numeric-report', 'someone-else')).toBeNull();
});
it('builds repair input containing both grounded abstract and experimental sources', async () => {
  const { report, ruleRun, finding } = await getPaperLintReportFinding({ reportId: 'numeric-report', userId: 'numeric-owner', ruleId: rule, findingId: 'd1' });
  const request = buildPaperLintReportRepairRequest({ report, ruleRun, finding, documentSha256: 'a'.repeat(64) });
  expect(request.evidence.some(e => e.text.includes('准确率92.5%'))).toBe(true);
  expect(request.evidence.some(e => e.text.includes('Accuracy89.3%'))).toBe(true);
  expect(request.rule.text).toContain('不编造正确值');
});
it('carries durable task ID into the detector and writes the resulting report', async () => {
  let invocation;
  const jobs = createPaperLintJobService({ runPaperLint: async args => {
    invocation = args;
    return { selectedRuleIds: [rule], result };
  } });
  const queued = await jobs.enqueue({ userId: 'numeric-owner', sourceFilename: 'job.pdf', pdfBuffer: Buffer.from('%PDF-test'), selectedRuleIds: [rule], externalProcessingConsent: true });
  await jobs.waitForIdle();
  const job = await jobs.getForUser(queued.job_id, 'numeric-owner');
  expect(invocation.runId).toBe(queued.job_id);
  expect(job.status).toBe('completed');
  expect((await reports.findPaperLintReportByIdForUser(job.report_id, 'numeric-owner')).selected_rule_ids).toEqual([rule]);
});
it('registers the numeric rule in the repository runner without an API call', async () => {
  const catalog = await getPaperLintCatalog({ refresh: true });
  expect(catalog.rules.find(r => r.rule_id === rule)).toMatchObject({ repair_supported: true, execution_mode: 'semantic' });
});
