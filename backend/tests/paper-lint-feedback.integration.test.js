import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import express from 'express';
import request from 'supertest';

const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const reportRepository = require('../src/normative/paperLintReportRepository');
const suggestionService = require('../src/normative/paperLintRepairSuggestionService');
const { buildPaperLintReportRepairRequest } = require('../src/normative/legacyRepairAdapter');
const { feedbackRouter } = require('../src/normative/paperLintFeedbackRoutes');
const { createPaperLintRepairSuggestionRouter } = require('../src/normative/paperLintRepairSuggestionRoutes');
const database = require('../src/database/db_runtime');

const harness = createTestDatabaseHarness({ label: 'paper-lint-feedback' });
const app = express();
app.use('/api/normative/feedback', feedbackRouter());
app.use('/api/normative/paper-lint', createPaperLintRepairSuggestionRouter());

beforeEach(async () => {
  const database = await harness.setup();
  await database.run("INSERT INTO auth_users (id,username,password_hash,role,scope) VALUES ('owner','owner','hash','STUDENT','COLLEGE'),('other','other','hash','STUDENT','COLLEGE')");
  await database.run("INSERT INTO auth_sessions (id,user_id,expires_at) VALUES ('owner-session','owner','2099-01-01T00:00:00.000Z'),('other-session','other','2099-01-01T00:00:00.000Z')");
  await reportRepository.createPaperLintReport({ userId: 'owner', sourceFilename: 'paper.pdf', pdfBuffer: Buffer.from('%PDF-1.7'), selectedRuleIds: ['sjtu_rule_15'], reportId: 'report-1', result: { rule_runs: [{ rule_id: 'sjtu_rule_15', findings: [{ finding_id: 'finding-15-1', message: '问题', location: { page_number: 1 } }] }] } });
});
afterEach(() => harness.cleanup());

describe('paper lint feedback', () => {
  it('reads saved-suggestion history only for the authenticated report owner', async () => {
    const url = '/api/normative/paper-lint/reports/report-1/repair-suggestions/history';
    await request(app).get(url).expect(401);
    await request(app).get(url).set('Cookie', 'arc_session=other-session').expect(404);
    await request(app).get(url).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.suggestions).toEqual([]));
  });
  it('persists response-speed feedback once for a repeated request ID', async () => {
    const input = {
      satisfaction_score: 4,
      improvement_areas: ['system_response_speed', 'detection_accuracy'],
      comment: '希望系统响应更快',
      request_id: 'response-speed-feedback',
    };
    const first = await request(app).post('/api/normative/feedback/system-feedback')
      .set('Cookie', 'arc_session=owner-session').send(input).expect(201);
    const retry = await request(app).post('/api/normative/feedback/system-feedback')
      .set('Cookie', 'arc_session=owner-session').send(input).expect(201);
    expect(retry.body).toMatchObject({ id: first.body.id, duplicate: true });
    const rows = await database.all('SELECT * FROM system_feedback WHERE user_id=?', ['owner']);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ satisfaction_score: 4, comment: '希望系统响应更快', request_id: 'response-speed-feedback' });
    expect(JSON.parse(rows[0].improvement_areas_json)).toEqual(['system_response_speed', 'detection_accuracy']);
  });

  it('rejects unknown improvement areas without storing feedback', async () => {
    await request(app).post('/api/normative/feedback/system-feedback')
      .set('Cookie', 'arc_session=owner-session')
      .send({ satisfaction_score: 4, improvement_areas: ['system_response_speed', 'unknown_area'] })
      .expect(400);
    expect(await database.all('SELECT id FROM system_feedback')).toEqual([]);
  });

  it('persists, updates, restores and cancels owner finding feedback', async () => {
    const url = '/api/normative/feedback/reports/report-1/findings/sjtu_rule_15/finding-15-1/feedback';
    await request(app).put(url).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'negative', reason_code: 'false_positive' }).expect(200);
    await request(app).get(url).set('Cookie', 'arc_session=owner-session').expect(200).expect(({ body }) => expect(body.feedback).toMatchObject({ feedback_value: 'negative', reason_code: 'false_positive' }));
    await request(app).put(url).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(200).expect(({ body }) => expect(body.feedback.reason_code).toBeNull());
    await request(app).delete(url).set('Cookie', 'arc_session=owner-session').expect(204);
    await request(app).get(url).set('Cookie', 'owner-session').expect(401);
  });

  it('isolates suggestion versions and validates system questionnaire', async () => {
    const { report, ruleRun, finding } = await suggestionService.getPaperLintReportFinding({ reportId: 'report-1', userId: 'owner', ruleId: 'sjtu_rule_15', findingId: 'finding-15-1' });
    const repair = buildPaperLintReportRepairRequest({ report, ruleRun, finding, documentSha256: 'document-hash' });
    const answer = { schema_version: 'repair-response-v2', source: repair.source, rule_id: 'sjtu_rule_15', finding_id: finding.finding_id, status: 'suggested', actions: [], provenance: { provider: 'huawei_maas', model: 'test', model_version: 'v1', prompt_version: 'p1', context_sha256: repair.context_sha256 }, usage: {} };
    const first = await suggestionService.savePaperLintRepairSuggestion(repair, 'owner', answer);
    const second = await suggestionService.savePaperLintRepairSuggestion(repair, 'owner', answer);
    await request(app).get('/api/normative/paper-lint/reports/report-1/repair-suggestions/history')
      .set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.suggestions.map((item) => item.id)).toEqual(expect.arrayContaining([first.suggestion_id, second.suggestion_id])));
    const firstUrl = `/api/normative/feedback/reports/report-1/repair-suggestions/${first.suggestion_id}/feedback`;
    await request(app).put(firstUrl).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'negative', reason_code: 'unclear' }).expect(200);
    const secondUrl = `/api/normative/feedback/reports/report-1/repair-suggestions/${second.suggestion_id}/feedback`;
    await request(app).get(secondUrl).set('Cookie', 'arc_session=owner-session').expect(200).expect(({ body }) => expect(body.feedback).toBeNull());
    await request(app).post('/api/normative/feedback/system-feedback').set('Cookie', 'arc_session=owner-session').send({ satisfaction_score: 0 }).expect(400);
    await request(app).post('/api/normative/feedback/system-feedback').set('Cookie', 'arc_session=owner-session').send({ satisfaction_score: 5, improvement_areas: ['ai_suggestion_quality'], comment: '很好' }).expect(201);
    await request(app).get(firstUrl).set('Cookie', 'arc_session=other-session').expect(404);
  });
});
