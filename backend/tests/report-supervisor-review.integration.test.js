import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');

const REQ_ID = 'FEAT-REPORT-SUPERVISOR-REVIEW';
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

async function seedSupervisorReviewUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'supervisor02', 'supervisor02', password_hash, 'SUPERVISOR', 'college01', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'supervisor01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor02', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
}

async function clearSupervisorReviewData() {
  await run('DELETE FROM supervisor_review_feedback');
  await run('DELETE FROM in_app_todos');
  await run('DELETE FROM report_submissions');
}

async function seedReviewTodo(overrides = {}) {
  const submissionId = overrides.submission_id || `${overrides.todo_id}-submission`;
  await run(
    `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      submissionId,
      overrides.batch_id || `${submissionId}-batch`,
      overrides.student_id || 'student01',
      overrides.supervisor_id || overrides.assignee_id || 'supervisor01',
      overrides.source_type || 'normative',
      overrides.report_id || `${submissionId}-report`,
      overrides.submission_status || 'submitted_pending_review',
      overrides.submission_created_at || overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
  await run(
    `INSERT INTO in_app_todos (id, submission_id, assignee_id, actor_id, status, title, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      overrides.todo_id,
      submissionId,
      overrides.assignee_id || 'supervisor01',
      overrides.actor_id || overrides.student_id || 'student01',
      overrides.todo_status || 'pending',
      overrides.title || '报告待批阅',
      overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
  return submissionId;
}

async function readSubmissionState(submissionId) {
  return get(
    `SELECT submission.status AS submission_status, todo.status AS todo_status
       FROM report_submissions AS submission
       INNER JOIN in_app_todos AS todo ON todo.submission_id = submission.id
      WHERE submission.id = ?`,
    [submissionId],
  );
}

describe('FEAT-REPORT-SUPERVISOR-REVIEW protected API and persistence contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-report-supervisor-review', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedSupervisorReviewUsers();
    await clearSupervisorReviewData();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-REPORT-SUPERVISOR-REVIEW:INTEGRATION:AUTHZ:001 denies anonymous and declared non-supervisor roles before report data or review writes', async () => {
    const submissionId = await seedReviewTodo({ todo_id: 'review-authz-supervisor01', assignee_id: 'supervisor01' });

    await request(app)
      .get(`/api/normative/supervisor-review-queue/${submissionId}`)
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.report).toBeUndefined();
      });

    await request(app)
      .post(`/api/normative/supervisor-review-queue/${submissionId}/review`)
      .send({ overall_evaluation: '匿名不应写入' })
      .expect(401);

    for (const username of ['student01', 'school_admin01', 'college_admin01']) {
      const cookie = await login(username);
      await request(app)
        .get(`/api/normative/supervisor-review-queue/${submissionId}`)
        .set('Cookie', cookie)
        .expect(403)
        .expect(({ body }) => {
          expect(body).toMatchObject({ code: 403 });
          expect(body.report).toBeUndefined();
        });

      await request(app)
        .post(`/api/normative/supervisor-review-queue/${submissionId}/review`)
        .set('Cookie', cookie)
        .send({ overall_evaluation: '非导师不应写入' })
        .expect(403);
    }

    const feedback = await get('SELECT id FROM supervisor_review_feedback WHERE submission_id = ?', [submissionId]);
    const state = await readSubmissionState(submissionId);
    expect(feedback).toBeNull();
    expect(state).toEqual({ submission_status: 'submitted_pending_review', todo_status: 'pending' });
  });

  it('FEAT-REPORT-SUPERVISOR-REVIEW:INTEGRATION:SCENARIO:001 submits annotations and required overall evaluation, then locks feedback and completes the todo', async () => {
    const submissionId = await seedReviewTodo({ todo_id: 'review-submit-supervisor01', assignee_id: 'supervisor01', report_id: 'normative-review-submit' });
    const cookie = await login('supervisor01');

    const detailResponse = await request(app)
      .get(`/api/normative/supervisor-review-queue/${submissionId}`)
      .set('Cookie', cookie)
      .expect(200);
    expect(detailResponse.body).toMatchObject({
      submission_id: submissionId,
      assignee_id: 'supervisor01',
      status: 'submitted_pending_review',
      todo_status: 'pending',
      review: { locked: false, annotations: [], overall_evaluation: null },
    });

    const response = await request(app)
      .post(`/api/normative/supervisor-review-queue/${submissionId}/review`)
      .set('Cookie', cookie)
      .send({
        annotations: [{ finding_id: 'finding-001', comment: '请补充该问题的依据说明' }],
        overall_evaluation: '整体达到批阅要求，但需要按批注整改。',
        improvement_suggestions: '请在下一轮提交前完成问题定位和文字修订。',
      })
      .expect(201);

    expect(response.body).toMatchObject({
      submission_id: submissionId,
      status: 'review_completed_feedback',
      todo_status: 'done',
      review: {
        locked: true,
        annotations: [{ finding_id: 'finding-001', comment: '请补充该问题的依据说明' }],
        overall_evaluation: '整体达到批阅要求，但需要按批注整改。',
        improvement_suggestions: '请在下一轮提交前完成问题定位和文字修订。',
      },
    });
    expect(response.body.review.submitted_at).toEqual(expect.any(String));

    const feedback = await get('SELECT annotations_json, overall_evaluation, improvement_suggestions FROM supervisor_review_feedback WHERE submission_id = ?', [submissionId]);
    expect(JSON.parse(feedback.annotations_json)).toEqual([{ finding_id: 'finding-001', comment: '请补充该问题的依据说明' }]);
    expect(feedback.overall_evaluation).toBe('整体达到批阅要求，但需要按批注整改。');
    expect(feedback.improvement_suggestions).toBe('请在下一轮提交前完成问题定位和文字修订。');
    await expect(readSubmissionState(submissionId)).resolves.toEqual({ submission_status: 'review_completed_feedback', todo_status: 'done' });

    await request(app)
      .post(`/api/normative/supervisor-review-queue/${submissionId}/review`)
      .set('Cookie', cookie)
      .send({ overall_evaluation: '锁定后不得重复提交' })
      .expect(409);
  });

  it('FEAT-REPORT-SUPERVISOR-REVIEW:INTEGRATION:VALIDATION:001 rejects blank overall evaluation before locking or changing status', async () => {
    const submissionId = await seedReviewTodo({ todo_id: 'review-missing-overall', assignee_id: 'supervisor01' });
    const cookie = await login('supervisor01');

    await request(app)
      .post(`/api/normative/supervisor-review-queue/${submissionId}/review`)
      .set('Cookie', cookie)
      .send({ annotations: [{ finding_id: 'finding-001', comment: '已有问题批注' }], overall_evaluation: '   ' })
      .expect(400)
      .expect(({ body }) => expect(body.message).toContain('整体评价'));

    const feedback = await get('SELECT id FROM supervisor_review_feedback WHERE submission_id = ?', [submissionId]);
    const state = await readSubmissionState(submissionId);
    expect(feedback).toBeNull();
    expect(state).toEqual({ submission_status: 'submitted_pending_review', todo_status: 'pending' });
  });

  it('FEAT-REPORT-SUPERVISOR-REVIEW:INTEGRATION:SCENARIO:002 returns 403 for non-assigned submissions and does not expose report or mutate state', async () => {
    const foreignSubmissionId = await seedReviewTodo({
      todo_id: 'review-foreign-supervisor02',
      assignee_id: 'supervisor02',
      supervisor_id: 'supervisor02',
      student_id: 'student02',
      actor_id: 'student02',
      report_id: 'foreign-report-must-not-leak',
    });
    const cookie = await login('supervisor01');

    await request(app)
      .get(`/api/normative/supervisor-review-queue/${foreignSubmissionId}`)
      .set('Cookie', cookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(JSON.stringify(body)).not.toContain('foreign-report-must-not-leak');
        expect(body.report).toBeUndefined();
      });

    await request(app)
      .post(`/api/normative/supervisor-review-queue/${foreignSubmissionId}/review`)
      .set('Cookie', cookie)
      .send({
        annotations: [{ finding_id: 'finding-foreign', comment: '不应写入' }],
        overall_evaluation: '不应允许非所属导师批阅',
      })
      .expect(403);

    const feedback = await get('SELECT id FROM supervisor_review_feedback WHERE submission_id = ?', [foreignSubmissionId]);
    const state = await readSubmissionState(foreignSubmissionId);
    expect(feedback).toBeNull();
    expect(state).toEqual({ submission_status: 'submitted_pending_review', todo_status: 'pending' });
  });
});
