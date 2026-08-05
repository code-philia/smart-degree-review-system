import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const repository = require('../src/normative/reportSupervisorQueueRepository');

const REQ_ID = 'FEAT-REPORT-SUPERVISOR-QUEUE';
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

async function seedSupervisorQueueUsers() {
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

async function seedQueueTodo(overrides = {}) {
  const submissionId = overrides.submission_id || `${overrides.todo_id}-submission`;
  await run(
    `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, 'submitted_pending_review', ?)`,
    [
      submissionId,
      overrides.batch_id || `${submissionId}-batch`,
      overrides.student_id || 'student01',
      overrides.supervisor_id || overrides.assignee_id || 'supervisor01',
      overrides.source_type || 'normative',
      overrides.report_id || `${submissionId}-report`,
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
      overrides.status || 'pending',
      overrides.title || '报告待批阅',
      overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
}

function recordIds(records) {
  return records.map((record) => record.todo_id);
}

describe('FEAT-REPORT-SUPERVISOR-QUEUE protected API, repository, and schema contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-report-supervisor-queue', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedSupervisorQueueUsers();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:INTEGRATION:AUTHZ:001 denies anonymous and declared non-supervisor roles before returning records or counts', async () => {
    await seedQueueTodo({ todo_id: 'queue-authz-supervisor01', assignee_id: 'supervisor01' });

    await request(app)
      .get('/api/normative/supervisor-review-queue')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.records).toBeUndefined();
      });

    for (const username of ['student01', 'school_admin01', 'college_admin01']) {
      const cookie = await login(username);
      await request(app)
        .get('/api/normative/supervisor-review-queue')
        .set('Cookie', cookie)
        .expect(403)
        .expect(({ body }) => {
          expect(body).toMatchObject({ code: 403 });
          expect(body.records).toBeUndefined();
        });

      await request(app)
        .get('/api/normative/supervisor-review-queue/badge')
        .set('Cookie', cookie)
        .expect(403)
        .expect(({ body }) => {
          expect(body).toMatchObject({ code: 403 });
          expect(body.unread_count).toBeUndefined();
        });
    }
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:INTEGRATION:SCENARIO:001 lists and counts only supervisor01 assignee todos through /api/normative', async () => {
    await seedQueueTodo({
      todo_id: 'queue-supervisor01-newer-pending',
      report_id: 'normative-supervisor01-newer',
      assignee_id: 'supervisor01',
      student_id: 'student01',
      source_type: 'normative',
      status: 'pending',
      created_at: '2026-08-05T12:00:00.000Z',
    });
    await seedQueueTodo({
      todo_id: 'queue-supervisor01-older-done',
      report_id: 'ai-supervisor01-older',
      assignee_id: 'supervisor01',
      student_id: 'student01',
      source_type: 'ai_review',
      status: 'done',
      created_at: '2026-08-05T13:00:00.000Z',
    });
    await seedQueueTodo({
      todo_id: 'queue-supervisor02-foreign-pending',
      report_id: 'normative-supervisor02-foreign',
      assignee_id: 'supervisor02',
      supervisor_id: 'supervisor02',
      student_id: 'student02',
      actor_id: 'student02',
      status: 'pending',
      created_at: '2026-08-05T14:00:00.000Z',
    });

    const cookie = await login('supervisor01');
    const response = await request(app)
      .get('/api/normative/supervisor-review-queue')
      .set('Cookie', cookie)
      .expect(200);

    expect(recordIds(response.body.records)).toEqual(['queue-supervisor01-newer-pending', 'queue-supervisor01-older-done']);
    expect(response.body.records[0]).toMatchObject({
      student_id: 'student01',
      assignee_id: 'supervisor01',
      source_type: 'normative',
      report_id: 'normative-supervisor01-newer',
      todo_status: 'pending',
    });
    expect(response.body.unread_count).toBe(1);
    expect(JSON.stringify(response.body)).not.toContain('supervisor02');
    expect(JSON.stringify(response.body)).not.toContain('student02');

    const badgeResponse = await request(app)
      .get('/api/normative/supervisor-review-queue/badge')
      .set('Cookie', cookie)
      .expect(200);
    expect(badgeResponse.body).toEqual({ unread_count: 1 });
  });

  it('FEAT-REPORT-SUPERVISOR-QUEUE:INTEGRATION:DB:001 orders pending first, then created_at descending, and applies student/type/status filters inside assignee scope', async () => {
    await seedQueueTodo({ todo_id: 'queue-order-done-newest', source_type: 'normative', status: 'done', created_at: '2026-08-05T13:00:00.000Z' });
    await seedQueueTodo({ todo_id: 'queue-order-pending-newest', source_type: 'ai_review', status: 'pending', created_at: '2026-08-05T12:00:00.000Z' });
    await seedQueueTodo({ todo_id: 'queue-order-pending-older', source_type: 'normative', status: 'pending', created_at: '2026-08-05T11:00:00.000Z' });
    await seedQueueTodo({
      todo_id: 'queue-order-foreign-pending',
      assignee_id: 'supervisor02',
      supervisor_id: 'supervisor02',
      student_id: 'student02',
      actor_id: 'student02',
      source_type: 'normative',
      status: 'pending',
      created_at: '2026-08-05T14:00:00.000Z',
    });

    const unfiltered = await repository.listSupervisorReviewTodos({ supervisorId: 'supervisor01', filters: {} });
    expect(recordIds(unfiltered.records)).toEqual([
      'queue-order-pending-newest',
      'queue-order-pending-older',
      'queue-order-done-newest',
    ]);
    expect(unfiltered.unread_count).toBe(2);

    const filtered = await repository.listSupervisorReviewTodos({
      supervisorId: 'supervisor01',
      filters: { student_id: 'student01', source_type: 'normative', status: 'pending' },
    });
    expect(recordIds(filtered.records)).toEqual(['queue-order-pending-older']);

    const badge = await repository.countIncompleteSupervisorReviewTodos({ supervisorId: 'supervisor01' });
    expect(badge).toEqual({ unread_count: 2 });
  });
});
