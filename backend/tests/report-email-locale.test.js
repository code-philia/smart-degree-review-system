import express from 'express';
import request from 'supertest';
import { afterAll, beforeAll, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness, get } = require('../src/database');
const authRoutes = require('../src/auth/authRoutes');
const { createReviewPilotPaperLintRouter } = require('../src/normative/reviewPilotPaperLintRoutes');
const { createPaperLintJobService } = require('../src/normative/paperLintJobService');
const repository = require('../src/normative/paperLintJobRepository');
const { createReportEmailService } = require('../src/notifications/reportEmailService');
const { reportEmail } = require('../src/notifications/reportEmailTemplate');
const settings = { origin: 'https://review.example.test', from: 'sender@sjtu.edu.cn', fromName: 'Test' };
const pdf = Buffer.from('%PDF-1.7\nlocale fixture');
const report = { id: 'sample', source_filename: 'Original论文.pdf' };
let harness, directory, app, cookie, jobs;
const engineArguments = [];
beforeAll(async () => {
  directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mail-locale-'));
  process.env.PAPER_LINT_JOBS_DIR = path.join(directory, 'jobs');
  process.env.PAPER_LINT_REPORTS_DIR = path.join(directory, 'reports');
  harness = createTestDatabaseHarness({ label: 'mail-locale', seedDefault: true });
  await harness.setup();
  const service = {
    MAX_PDF_BYTES: 50 * 1024 * 1024, validatePdf() {},
    normalizeSelectedRuleIds: async ids => ids,
    runPaperLint: async args => {
      engineArguments.push(args);
      return { result: { type: 'paper_lint', ruleset: { id: 'test', version_label: 'test' }, summary: {},
        rule_runs: args.selectedRuleIds.map(rule_id => ({ rule_id, execution_status: 'completed', outcome: 'passed', severity: 'warning', findings: [] })) }, selectedRuleIds: args.selectedRuleIds };
    },
  };
  jobs = createPaperLintJobService(service);
  app = express();
  app.use('/api/auth', express.json(), authRoutes);
  app.use('/api/normative/paper-lint', createReviewPilotPaperLintRouter(service, undefined, jobs));
  const login = await request(app).post('/api/auth/login').send({ username: 'student01', password: 'ArcDemo123!' }).expect(200);
  cookie = login.headers['set-cookie'].find(value => value.startsWith('arc_session='));
});
afterAll(async () => {
  await jobs.waitForIdle();
  await harness.cleanup();
  fs.rmSync(directory, { recursive: true, force: true });
  delete process.env.PAPER_LINT_JOBS_DIR;
  delete process.env.PAPER_LINT_REPORTS_DIR;
});
it.each(['zh', 'en'])('renders only the %s letter, subject and action without any signoff or signature', locale => {
  const mail = reportEmail(report, 'reader@example.test', settings, 'job', locale);
  const title = locale === 'en' ? 'Your thesis report is ready' : '论文检测报告已生成';
  const otherTitle = locale === 'en' ? '论文检测报告已生成' : 'Your thesis report is ready';
  for (const content of [mail.subject, mail.text, mail.html]) {
    expect(content).toContain(title);
    expect(content).not.toContain(otherTitle);
    expect(content).not.toMatch(/祝好|Best regards|研究生学位信息系统|Graduate Degree Information System/);
    expect(content).toContain(report.source_filename);
  }
  expect(mail.subject).toBe((locale === 'en' ? '[Smart Degree · AI Review Assistant] ' : '【智慧学位 AI 评阅辅助系统】') + title + ' | ' + report.source_filename);
  for (const content of [mail.text, mail.html]) expect(content).not.toMatch(/智慧学位|Smart Degree/);
  expect(mail.html.match(/<a /g)).toHaveLength(1);
  expect(mail.html).toContain(`/reports/pdf/sample?lang=${locale}`);
  expect(mail.text).toContain(`/reports/pdf/sample?lang=${locale}`);
  expect(mail.html).not.toContain(`?lang=${locale === 'en' ? 'zh' : 'en'}`);
  expect(mail.html).toContain('font-size:14px;font-weight:400;line-height:22px');
  expect(mail.html).toContain('font-size:18px;font-weight:600;line-height:26px');
  expect(mail.messageId).toBe('<report-job@sjtu.edu.cn>');
});
it.each([undefined, '', 'EN', 'de', '<script>'])('defaults missing or unsupported locale %s to Chinese', locale => {
  const mail = reportEmail(report, 'reader@example.test', settings, 'job', locale);
  expect(mail.text).toContain('您的论文检测报告已生成');
  expect(mail.html).not.toContain('Your thesis report is ready');
});
it('retains the submitted language through normal upload, request replay, incremental rerun and delivery retry', async () => {
  const sent = [], attempted = [];
  let clock = Date.now() + 1000;
  const submit = locale => request(app).post('/api/normative/paper-lint/run?filename=Original论文.pdf')
    .set('Cookie', cookie).set('Content-Type', 'application/pdf')
    .set('X-Paper-Lint-Rule-Ids', 'sjtu_rule_18').set('X-Paper-Lint-Request-Id', 'locale-upload')
    .set('X-Paper-Lint-Notification-Locale', locale).send(pdf).expect(202);
  const first = await submit('en');
  await jobs.waitForIdle();
  expect((await repository.getJob(first.body.job_id)).status).toBe('completed');
  // The same accepted request must retain its original language after switching UI language.
  const replay = await submit('zh');
  expect(replay.body.job_id).toBe(first.body.job_id);
  await jobs.waitForIdle();
  expect((await repository.getJob(first.body.job_id)).notification_locale).toBe('en');
  const rerun = await request(app).post(`/api/normative/paper-lint/reports/${first.body.job_id}/rerun`)
    .set('Cookie', cookie).set('X-Paper-Lint-Notification-Locale', 'zh')
    .set('X-Paper-Lint-Request-Id', 'locale-rerun').send({ selected_rule_ids: ['sjtu_rule_22'] }).expect(202);
  await jobs.waitForIdle();
  expect((await repository.getJob(rerun.body.job_id)).notification_locale).toBe('zh');
  expect((await repository.getJob(rerun.body.job_id)).error_message).toBeNull();
  expect((await repository.getJob(rerun.body.job_id)).status).toBe('completed');
  // Mail preference must not be passed to the detection engine.
  for (const args of engineArguments) expect(args).not.toHaveProperty('notificationLocale');
  const worker = createReportEmailService({ config: () => settings, now: () => clock, send: async mail => {
    attempted.push(mail);
    if (attempted.length === 1) throw new Error('temporary delivery failure');
    sent.push(mail);
  } });
  await worker.drain();
  expect(sent).toHaveLength(1);
  expect(sent[0].text).toContain('您的论文检测报告已生成');
  const retry = await get('SELECT next_attempt_at FROM report_email_outbox WHERE job_id=?', [first.body.job_id]);
  clock = Date.parse(retry.next_attempt_at) + 1;
  await worker.drain();
  expect(sent).toHaveLength(2);
  expect(sent[1].text).toContain('Your thesis report is ready.');
  expect(attempted[0]).toEqual(sent[1]);
  expect((await get('SELECT attempts FROM report_email_outbox WHERE job_id=?', [first.body.job_id])).attempts).toBe(2);
});
it('normalizes an invalid locale at persistence and leaves cancellations without queued mail', async () => {
  const id = await repository.createJob({ userId: 'student01', sourceFilename: 'cancel.pdf', pdfBuffer: pdf,
    selectedRuleIds: [], notificationLocale: 'invalid' });
  expect((await repository.getJob(id)).notification_locale).toBe('zh');
  await jobs.cancelForUser(id, 'student01');
  expect(await repository.completeJob(id, id)).toBe(false);
  expect(await get('SELECT * FROM report_email_outbox WHERE job_id=?', [id])).toBeNull();
});
