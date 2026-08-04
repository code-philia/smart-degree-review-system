import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const {
  buildDownloadReportPayload,
  getDetectionReportForUser,
  listDetectionReportsForUser,
} = require('../src/normative/detectionReportService');

const REQ_ID = 'FEAT-NORMATIVE-REPORT';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

function cookieValue(response) {
  return response.headers['set-cookie']?.find((cookie) => cookie.startsWith('arc_session='));
}

async function login(username) {
  const response = await request(app)
    .post('/api/auth/login')
    .send({ username, password: demoPassword })
    .expect(200);
  return cookieValue(response);
}

function reportIssue(overrides = {}) {
  return {
    rule_id: 'NORM-002',
    category: '标点配对',
    severity: 'high',
    line: 3,
    column: 6,
    excerpt: '未配对（括号',
    message: '圆括号未成对',
    suggestion: '补全或删除未配对的括号',
    ...overrides,
  };
}

async function seedReport(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || '学生报告.txt',
    original_text: overrides.original_text || ['摘要', '关键词', '这里有未配对（括号。'].join('\n'),
    rule_snapshot: overrides.rule_snapshot || [{ rule_id: 'NORM-002', title: '标点配对', severity: 'high' }],
    issues: overrides.issues || [reportIssue()],
    severity_counts: overrides.severity_counts || { high: 1, medium: 0, low: 0 },
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  });
}

describe('FEAT-NORMATIVE-REPORT owned report API and service contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-normative-report', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-NORMATIVE-REPORT:API:001 denies anonymous history, detail, and JSON download at the backend boundary', async () => {
    const ownedReport = await seedReport({ id: 'report-anonymous-boundary' });

    await request(app).get('/api/normative/detection-reports').expect(401);
    await request(app).get(`/api/normative/detection-reports/${ownedReport.id}`).expect(401);
    await request(app).get(`/api/normative/detection-reports/${ownedReport.id}/download`).expect(401);
  });

  it('FEAT-NORMATIVE-REPORT:API:002 lists only the authenticated student history in created-time descending order', async () => {
    await seedReport({ id: 'student-old-report', created_at: '2026-08-04T09:00:00.000Z', source_filename: '旧报告.txt' });
    await seedReport({ id: 'student-new-report', created_at: '2026-08-04T11:00:00.000Z', source_filename: '新报告.txt' });
    await seedReport({ id: 'other-user-report', user_id: 'supervisor01', created_at: '2026-08-04T12:00:00.000Z', source_filename: '他人报告.txt' });
    const cookie = await login('student01');

    await request(app)
      .get('/api/normative/detection-reports')
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.records.map((record) => record.id)).toEqual(
          expect.arrayContaining(['student-new-report', 'student-old-report']),
        );
        expect(body.records.find((record) => record.id === 'other-user-report')).toBeUndefined();
        const newIndex = body.records.findIndex((record) => record.id === 'student-new-report');
        const oldIndex = body.records.findIndex((record) => record.id === 'student-old-report');
        expect(newIndex).toBeGreaterThanOrEqual(0);
        expect(oldIndex).toBeGreaterThanOrEqual(0);
        expect(newIndex).toBeLessThan(oldIndex);
        const newest = body.records[newIndex];
        expect(newest).toMatchObject({
          source_filename: '新报告.txt',
          severity_counts: { high: 1, medium: 0, low: 0 },
        });
        expect(newest.issues[0]).toMatchObject({ line: 3, column: 6, excerpt: '未配对（括号' });
      });
  });

  it('FEAT-NORMATIVE-REPORT:API:003 returns 404 for another user report id and exports complete UTF-8 JSON payload for the owner', async () => {
    const ownReport = await seedReport({
      id: 'student-download-report',
      rule_snapshot: [{ rule_id: 'NORM-002', title: '标点配对' }, { rule_id: 'NORM-003', title: '重复标点' }],
      issues: [reportIssue(), reportIssue({ rule_id: 'NORM-003', severity: 'medium', column: 12, excerpt: '。。' })],
      severity_counts: { high: 1, medium: 1, low: 0 },
    });
    const otherReport = await seedReport({ id: 'supervisor-owned-report', user_id: 'supervisor01' });
    const cookie = await login('student01');

    await request(app)
      .get(`/api/normative/detection-reports/${otherReport.id}`)
      .set('Cookie', cookie)
      .expect(404);

    await request(app)
      .get(`/api/normative/detection-reports/${ownReport.id}/download`)
      .set('Cookie', cookie)
      .expect(200)
      .expect('content-type', /application\/json; charset=utf-8/)
      .expect('content-disposition', new RegExp(`attachment; filename="normative-report-${ownReport.id}\\.json"`))
      .expect(({ body }) => {
        expect(body).toMatchObject({
          id: ownReport.id,
          source_filename: '学生报告.txt',
          status: 'completed',
          severity_counts: { high: 1, medium: 1, low: 0 },
          original_text: ownReport.original_text,
        });
        expect(body.rule_snapshot).toHaveLength(2);
        expect(body.issues).toHaveLength(2);
        expect(body.issues[1]).toMatchObject({ rule_id: 'NORM-003', excerpt: '。。' });
      });
  });

  it('FEAT-NORMATIVE-REPORT:FUNC:001 scopes service reads by owner and shapes deterministic download payloads', async () => {
    const report = await seedReport({ id: 'service-owned-report', created_at: '2026-08-04T13:00:00.000Z' });

    await expect(listDetectionReportsForUser(null)).rejects.toMatchObject({ status: 401 });
    await expect(getDetectionReportForUser({ username: 'student01' }, '')).rejects.toMatchObject({ status: 400 });
    await expect(getDetectionReportForUser({ username: 'supervisor01' }, report.id)).rejects.toMatchObject({ status: 404 });
    await expect(getDetectionReportForUser({ username: 'student01' }, report.id)).resolves.toMatchObject({ id: report.id });
    expect(buildDownloadReportPayload(report)).toEqual({
      id: report.id,
      source_filename: report.source_filename,
      created_at: report.created_at,
      status: report.status,
      severity_counts: report.severity_counts,
      rule_snapshot: report.rule_snapshot,
      issues: report.issues,
      original_text: report.original_text,
    });
  });
});
