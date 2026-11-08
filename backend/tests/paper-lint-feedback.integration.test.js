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


const numericRule = 'abstract_numeric_consistency_check';
const warningUrl = (ruleId, findingId) => `/api/normative/feedback/reports/report-1/findings/${encodeURIComponent(ruleId)}/${encodeURIComponent(findingId)}/feedback`;
async function replaceRuns(runs) {
  const resultJson = JSON.stringify({ rule_runs: runs });
  await database.run('UPDATE paper_lint_reports SET result_json=? WHERE id=?', [resultJson, 'report-1']);
  return resultJson;
}

describe('execution warning feedback through the existing finding-feedback API', () => {
  it('persists, restores, changes and cancels a numeric precondition warning without rewriting the report', async () => {
    const original = await replaceRuns([{ rule_id: numericRule, execution_status: 'completed', params: { preconditions: [
      { id: 'abstract_numeric', passed: false, status: 'failed' },
      { id: 'contribution_mapping', passed: false, status: 'skipped' },
    ] }, findings: [] }]);
    const url = warningUrl(numericRule, `execution-warning:${numericRule}:precondition:abstract_numeric`);
    await request(app).put(url).set('Cookie', 'arc_session=owner-session')
      .send({ feedback_value: 'negative', reason_code: 'false_positive', reason_text: '摘要中已有数值' }).expect(200);
    await request(app).get(url).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.feedback).toMatchObject({ feedback_value: 'negative', reason_code: 'false_positive', reason_text: '摘要中已有数值' }));
    await request(app).put(url).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(200)
      .expect(({ body }) => expect(body.feedback).toMatchObject({ feedback_value: 'positive', reason_code: null, reason_text: null }));
    await request(app).delete(url).set('Cookie', 'arc_session=owner-session').expect(204);
    await request(app).get(url).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.feedback).toBeNull());
    expect((await database.get('SELECT result_json FROM paper_lint_reports WHERE id=?', ['report-1'])).result_json).toBe(original);
  });

  it('keeps duplicate preconditions and run failure feedback separate', async () => {
    await replaceRuns([{ rule_id: numericRule, execution_status: 'error', params: { preconditions: [
      { id: 'abstract_numeric', passed: false }, { id: 'abstract_numeric', passed: false },
    ] }, findings: [] }]);
    const ids = [`execution-warning:${numericRule}:precondition:abstract_numeric`, `execution-warning:${numericRule}:precondition:abstract_numeric:2`, `execution-warning:${numericRule}:failure`];
    for (const [index, id] of ids.entries()) {
      await request(app).put(warningUrl(numericRule, id)).set('Cookie', 'arc_session=owner-session')
        .send({ feedback_value: 'negative', reason_code: 'other', reason_text: `warning ${index}` }).expect(200);
    }
    for (const [index, id] of ids.entries()) {
      await request(app).get(warningUrl(numericRule, id)).set('Cookie', 'arc_session=owner-session').expect(200)
        .expect(({ body }) => expect(body.feedback.reason_text).toBe(`warning ${index}`));
    }
  });

  it('does not collide with a raw finding ID using the warning namespace', async () => {
    const rawId = `execution-warning:${numericRule}:precondition:abstract_numeric`;
    await replaceRuns([{ rule_id: numericRule, execution_status: 'completed', params: { preconditions: [{ id: 'abstract_numeric', passed: false }] }, findings: [{ finding_id: rawId, rule_id: numericRule, message: 'raw finding' }] }]);
    await request(app).put(warningUrl(numericRule, rawId)).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(200);
    await request(app).put(warningUrl(numericRule, `${rawId}:2`)).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'negative' }).expect(200);
    await request(app).get(warningUrl(numericRule, rawId)).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.feedback.feedback_value).toBe('positive'));
    await request(app).get(warningUrl(numericRule, `${rawId}:2`)).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.feedback.feedback_value).toBe('negative'));
  });

  it('allows existing generic warnings without enabling AI repairs or unsupported actual findings', async () => {
    const ruleId = 'saved_custom_rule';
    await replaceRuns([{ rule_id: ruleId, execution_status: 'unsupported', findings: [{ finding_id: 'raw', message: 'raw finding' }] }]);
    await request(app).put(warningUrl(ruleId, `execution-warning:${ruleId}:generic`)).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(200);
    await request(app).put(warningUrl(ruleId, 'raw')).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(422);
    await expect(suggestionService.getPaperLintReportFinding({ reportId: 'report-1', userId: 'owner', ruleId, findingId: `execution-warning:${ruleId}:generic` })).rejects.toMatchObject({ status: 422 });
  });

  it('rejects absent, skipped and forged warnings and enforces report ownership', async () => {
    await replaceRuns([{ rule_id: numericRule, execution_status: 'completed', params: { preconditions: [{ id: 'abstract_numeric', passed: false, status: 'skipped' }] }, findings: [] }]);
    const id = `execution-warning:${numericRule}:precondition:abstract_numeric`;
    for (const findingId of [id, `execution-warning:${numericRule}:failure`, `execution-warning:${numericRule}:forged`]) {
      await request(app).put(warningUrl(numericRule, findingId)).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(404);
    }
    await request(app).get(warningUrl(numericRule, id)).expect(401);
    await request(app).get(warningUrl(numericRule, id)).set('Cookie', 'arc_session=other-session').expect(404);
    expect(await database.all('SELECT id FROM paper_lint_finding_feedback')).toEqual([]);
  });

  it('persists a reference resource warning beside actual findings using the same owner boundary', async () => {
    const ruleId = 'sjtu_rule_32';
    const original = await replaceRuns([{ rule_id: ruleId, execution_status: 'completed', outcome: 'issues_found', params: { reference_resources_unavailable: true, reference_verification: { unresolved: 1, unavailable: 1 } }, findings: [
      { finding_id: 'real-reference', rule_id: ruleId, message: '已有检索结果', reference_review: 'supported_suspicion' },
    ] }]);
    const url = warningUrl(ruleId, `execution-warning:${ruleId}:generic`);
    await request(app).put(url).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'positive' }).expect(200);
    await request(app).get(url).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.feedback.feedback_value).toBe('positive'));
    await request(app).get(warningUrl(ruleId, 'real-reference')).set('Cookie', 'arc_session=owner-session').expect(200)
      .expect(({ body }) => expect(body.feedback).toBeNull());
    for (const method of ['get', 'put', 'delete']) {
      await request(app)[method](url).set('Cookie', 'arc_session=other-session').send({ feedback_value: 'negative' }).expect(404);
    }
    expect((await database.get('SELECT result_json FROM paper_lint_reports WHERE id=?', ['report-1'])).result_json).toBe(original);
  });

  it('validates negative warning feedback before storing it', async () => {
    const ruleId = 'keyword_count_check';
    await replaceRuns([{ rule_id: ruleId, execution_status: 'error', findings: [] }]);
    const url = warningUrl(ruleId, `execution-warning:${ruleId}:generic`);
    await request(app).put(url).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'negative', reason_code: 'forged' }).expect(400);
    await request(app).put(url).set('Cookie', 'arc_session=owner-session').send({ feedback_value: 'negative', reason_text: 'x'.repeat(1001) }).expect(400);
    expect(await database.all('SELECT id FROM paper_lint_finding_feedback')).toEqual([]);
  });
});
