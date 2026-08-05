import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');

const REQ_ID = 'FEAT-REPORT-STUDENT-SUBMIT';
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

async function seedCompletedNormativeReport(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: overrides.status || 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || '学生可提交规范报告.txt',
    original_text: '摘要\n关键词\n结论',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '章节完整性' }],
    issues: [],
    severity_counts: { high: 0, medium: 0, low: 0 },
    created_at: overrides.created_at || '2026-08-05T09:00:00.000Z',
  });
}

async function countSubmissionSideEffects() {
  const submissions = await get('SELECT COUNT(*) AS total FROM report_submissions');
  const todos = await get('SELECT COUNT(*) AS total FROM in_app_todos');
  return { submissions: submissions.total, todos: todos.total };
}

describe('FEAT-REPORT-STUDENT-SUBMIT protected submission API and persistence contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-report-student-submit-api', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM in_app_todos');
    await run('DELETE FROM report_submissions');
    await run('DELETE FROM normative_detection_tasks');
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:INTEGRATION:AUTHZ:001 denies anonymous and declared non-student roles before creating records or todos', async () => {
    const report = await seedCompletedNormativeReport({ id: 'student01-authz-report' });

    await request(app)
      .post('/api/normative/report-submissions')
      .send({ reports: [{ source_type: 'normative', report_id: report.id }] })
      .expect(401);

    for (const username of ['supervisor01', 'school_admin01', 'college_admin01']) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/report-submissions')
        .set('Cookie', cookie)
        .send({ reports: [{ source_type: 'normative', report_id: report.id }] })
        .expect(403)
        .expect(({ body }) => {
          expect(body.code).toBe(403);
          expect(body.submissions).toBeUndefined();
          expect(body.todos).toBeUndefined();
        });
    }

    await expect(countSubmissionSideEffects()).resolves.toEqual({ submissions: 0, todos: 0 });
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:INTEGRATION:SCENARIO:001 lets student01 submit an owned completed report and creates a supervisor01 todo in the same batch', async () => {
    const report = await seedCompletedNormativeReport({ id: 'student01-owned-completed-report' });
    const cookie = await login('student01');

    const response = await request(app)
      .post('/api/normative/report-submissions')
      .set('Cookie', cookie)
      .send({ reports: [{ source_type: 'normative', report_id: report.id }] })
      .expect(201);

    expect(response.body).toMatchObject({
      batch_id: expect.any(String),
      submissions: [
        {
          id: expect.any(String),
          student_id: 'student01',
          supervisor_id: 'supervisor01',
          source_type: 'normative',
          report_id: report.id,
          status: 'submitted_pending_review',
          created_at: expect.any(String),
        },
      ],
      todos: [
        {
          id: expect.any(String),
          assignee_id: 'supervisor01',
          actor_id: 'student01',
          status: 'pending',
          title: expect.stringMatching(/报告|批阅/),
          created_at: expect.any(String),
        },
      ],
    });
    expect(response.body.submissions[0].batch_id).toBe(response.body.batch_id);
    expect(response.body.todos[0].submission_id).toBe(response.body.submissions[0].id);

    const persistedSubmission = await get(
      `SELECT batch_id AS batchId, student_id AS studentId, supervisor_id AS supervisorId,
              source_type AS sourceType, report_id AS reportId, status
         FROM report_submissions
        WHERE id = ?`,
      [response.body.submissions[0].id],
    );
    const persistedTodo = await get(
      `SELECT submission_id AS submissionId, assignee_id AS assigneeId, actor_id AS actorId, status, title
         FROM in_app_todos
        WHERE id = ?`,
      [response.body.todos[0].id],
    );

    expect(persistedSubmission).toEqual({
      batchId: response.body.batch_id,
      studentId: 'student01',
      supervisorId: 'supervisor01',
      sourceType: 'normative',
      reportId: report.id,
      status: 'submitted_pending_review',
    });
    expect(persistedTodo).toMatchObject({
      submissionId: response.body.submissions[0].id,
      assigneeId: 'supervisor01',
      actorId: 'student01',
      status: 'pending',
    });
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:INTEGRATION:SCENARIO:002 returns 403 for another user report id and creates no submission or todo', async () => {
    const foreignReport = await seedCompletedNormativeReport({
      id: 'supervisor-owned-completed-report',
      user_id: 'supervisor01',
      source_filename: '导师报告不可提交.txt',
    });
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/report-submissions')
      .set('Cookie', cookie)
      .send({ reports: [{ source_type: 'normative', report_id: foreignReport.id }] })
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.submissions).toBeUndefined();
        expect(body.todos).toBeUndefined();
      });

    await expect(countSubmissionSideEffects()).resolves.toEqual({ submissions: 0, todos: 0 });
  });

  it('FEAT-REPORT-STUDENT-SUBMIT:INTEGRATION:TRANSACTION:001 rejects mixed valid and foreign batches without partial writes', async () => {
    const ownedReport = await seedCompletedNormativeReport({ id: 'student01-valid-mixed-report' });
    const foreignReport = await seedCompletedNormativeReport({ id: 'student01-invalid-mixed-report', user_id: 'supervisor01' });
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/report-submissions')
      .set('Cookie', cookie)
      .send({
        reports: [
          { source_type: 'normative', report_id: ownedReport.id },
          { source_type: 'normative', report_id: foreignReport.id },
        ],
      })
      .expect(403);

    await expect(countSubmissionSideEffects()).resolves.toEqual({ submissions: 0, todos: 0 });
  });
});
