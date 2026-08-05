import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, all, get, run } = require('../src/database');

const REQ_ID = 'FEAT-REPORT-STUDENT-RESULTS';
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

async function seedStudentResultsUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor01', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
}

async function clearStudentResultsData() {
  await run('DELETE FROM supervisor_review_feedback');
  await run('DELETE FROM in_app_todos');
  await run('DELETE FROM report_submissions');
}

async function seedReviewedSubmission(overrides = {}) {
  const submissionId = overrides.submission_id || `student-result-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  await run(
    `INSERT INTO report_submissions (id, batch_id, student_id, supervisor_id, source_type, report_id, status, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
    [
      submissionId,
      overrides.batch_id || `${submissionId}-batch`,
      overrides.student_id || 'student01',
      overrides.supervisor_id || 'supervisor01',
      overrides.source_type || 'normative',
      overrides.report_id || `${submissionId}-report`,
      overrides.status || 'review_completed_feedback',
      overrides.created_at || '2026-08-05T09:00:00.000Z',
    ],
  );
  await run(
    `INSERT INTO supervisor_review_feedback (id, submission_id, supervisor_id, annotations_json, overall_evaluation, improvement_suggestions, locked_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    [
      overrides.feedback_id || `${submissionId}-feedback`,
      submissionId,
      overrides.supervisor_id || 'supervisor01',
      JSON.stringify(overrides.annotations || [{ finding_id: 'finding-001', comment: '请补充研究依据。' }]),
      overrides.overall_evaluation || '整体评价：本轮报告已完成批阅。',
      overrides.improvement_suggestions || '整改建议：逐条回应 finding 批注。',
      overrides.locked_at || '2026-08-05T10:00:00.000Z',
    ],
  );
  return submissionId;
}

async function submissionStatus(submissionId) {
  const row = await get('SELECT status FROM report_submissions WHERE id = ?', [submissionId]);
  return row?.status;
}

function resultIds(results) {
  return results.map((record) => record.submission_id);
}

describe('FEAT-REPORT-STUDENT-RESULTS protected API, repository, and first-view contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-report-student-results', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedStudentResultsUsers();
    await clearStudentResultsData();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-REPORT-STUDENT-RESULTS:INTEGRATION:AUTHZ:001 denies anonymous and declared non-student roles before returning result data or mutating state', async () => {
    const submissionId = await seedReviewedSubmission({ submission_id: 'student-result-authz-owned' });

    for (const endpoint of [
      '/api/normative/student-report-results',
      `/api/normative/student-report-results/${submissionId}`,
      `/api/normative/student-report-results/${submissionId}/download`,
    ]) {
      await request(app)
        .get(endpoint)
        .expect(401)
        .expect(({ body }) => {
          expect(body).toMatchObject({ code: 401 });
          expect(JSON.stringify(body)).not.toContain('整体评价：本轮报告已完成批阅。');
        });
    }

    for (const username of ['supervisor01', 'school_admin01', 'college_admin01']) {
      const cookie = await login(username);
      await request(app)
        .get('/api/normative/student-report-results')
        .set('Cookie', cookie)
        .expect(403)
        .expect(({ body }) => {
          expect(body).toMatchObject({ code: 403 });
          expect(body.results).toBeUndefined();
        });
      await request(app)
        .get(`/api/normative/student-report-results/${submissionId}`)
        .set('Cookie', cookie)
        .expect(403);
      await request(app)
        .get(`/api/normative/student-report-results/${submissionId}/download`)
        .set('Cookie', cookie)
        .expect(403);
    }

    await expect(submissionStatus(submissionId)).resolves.toBe('review_completed_feedback');
  });

  it('FEAT-REPORT-STUDENT-RESULTS:INTEGRATION:FILTERS:001 lists only student-owned feedback rounds and applies time, report type, and status filters in the API path', async () => {
    const newestOwned = await seedReviewedSubmission({
      submission_id: 'student-result-owned-newest',
      report_id: 'normative-owned-newest',
      source_type: 'normative',
      status: 'review_completed_feedback',
      created_at: '2026-08-05T12:00:00.000Z',
    });
    const viewedOwned = await seedReviewedSubmission({
      submission_id: 'student-result-owned-viewed',
      report_id: 'ai-owned-viewed',
      source_type: 'ai_review',
      status: 'student_viewed_feedback',
      created_at: '2026-08-04T12:00:00.000Z',
    });
    await seedReviewedSubmission({
      submission_id: 'student-result-foreign',
      student_id: 'student02',
      report_id: 'foreign-result-must-not-leak',
      created_at: '2026-08-05T13:00:00.000Z',
    });

    const cookie = await login('student01');
    const unfiltered = await request(app)
      .get('/api/normative/student-report-results')
      .set('Cookie', cookie)
      .expect(200);

    expect(resultIds(unfiltered.body.results)).toEqual([newestOwned, viewedOwned]);
    expect(JSON.stringify(unfiltered.body)).not.toContain('foreign-result-must-not-leak');

    const filtered = await request(app)
      .get('/api/normative/student-report-results')
      .query({ from: '2026-08-05', to: '2026-08-06', source_type: 'normative', status: 'review_completed_feedback' })
      .set('Cookie', cookie)
      .expect(200);

    expect(resultIds(filtered.body.results)).toEqual([newestOwned]);
    expect(filtered.body.results[0]).toMatchObject({
      source_type: 'normative',
      report_id: 'normative-owned-newest',
      status: 'review_completed_feedback',
      feedback_at: '2026-08-05T10:00:00.000Z',
    });
  });

  it('FEAT-REPORT-STUDENT-RESULTS:INTEGRATION:SCENARIO:001 opens completed feedback detail, returns annotations and evaluation, and marks it student_viewed_feedback', async () => {
    const submissionId = await seedReviewedSubmission({
      submission_id: 'student-result-first-open',
      batch_id: 'student-result-history-batch',
      report_id: 'normative-first-open-report',
      annotations: [{ finding_id: 'finding-001', comment: '请补充该 finding 的定位依据。' }],
      overall_evaluation: '整体评价：批阅完成，允许学生查阅。',
      improvement_suggestions: '整改建议：下一轮提交前逐条回复批注。',
    });
    await seedReviewedSubmission({
      submission_id: 'student-result-history-round',
      batch_id: 'student-result-history-batch',
      report_id: 'normative-first-open-report',
      status: 'student_viewed_feedback',
      created_at: '2026-08-04T09:00:00.000Z',
    });
    await seedReviewedSubmission({
      submission_id: 'student-result-unrelated-round',
      report_id: 'unrelated-report',
      status: 'student_viewed_feedback',
      created_at: '2026-08-03T09:00:00.000Z',
    });

    const cookie = await login('student01');
    const response = await request(app)
      .get(`/api/normative/student-report-results/${submissionId}`)
      .set('Cookie', cookie)
      .expect(200);

    expect(response.body).toMatchObject({
      submission_id: submissionId,
      status: 'student_viewed_feedback',
      report: { title: 'normative-first-open-report' },
      review: {
        annotations: [{ finding_id: 'finding-001', comment: '请补充该 finding 的定位依据。' }],
        overall_evaluation: '整体评价：批阅完成，允许学生查阅。',
        improvement_suggestions: '整改建议：下一轮提交前逐条回复批注。',
      },
    });
    expect(response.body.report.original_text).toEqual(expect.any(String));
    expect(response.body.history_rounds.map((round) => round.submission_id)).toEqual([submissionId, 'student-result-history-round']);
    await expect(submissionStatus(submissionId)).resolves.toBe('student_viewed_feedback');
  });

  it('FEAT-REPORT-STUDENT-RESULTS:INTEGRATION:DOWNLOAD:001 returns deterministic JSON summary, annotations, evaluation, and suggestions for an owned result', async () => {
    const submissionId = await seedReviewedSubmission({
      submission_id: 'student-result-download',
      report_id: 'downloadable-report',
      annotations: [{ finding_id: 'finding-download', comment: '下载中应包含批注。' }],
      overall_evaluation: '整体评价：下载 JSON 应包含该评价。',
      improvement_suggestions: '整改建议：下载 JSON 应包含该建议。',
    });
    const cookie = await login('student01');

    const response = await request(app)
      .get(`/api/normative/student-report-results/${submissionId}/download`)
      .set('Cookie', cookie)
      .expect(200)
      .expect('Content-Type', /application\/json/);

    expect(response.headers['content-disposition']).toContain(`student-report-result-${submissionId}.json`);
    expect(response.body).toEqual({
      submission_id: submissionId,
      report_summary: {
        submission_id: submissionId,
        batch_id: `${submissionId}-batch`,
        source_type: 'normative',
        report_id: 'downloadable-report',
        status: 'student_viewed_feedback',
        submitted_at: '2026-08-05T09:00:00.000Z',
        feedback_at: '2026-08-05T10:00:00.000Z',
      },
      annotations: [{ finding_id: 'finding-download', comment: '下载中应包含批注。' }],
      overall_evaluation: '整体评价：下载 JSON 应包含该评价。',
      improvement_suggestions: '整改建议：下载 JSON 应包含该建议。',
    });
    const rows = await all('SELECT status FROM report_submissions WHERE id = ?', [submissionId]);
    expect(rows).toEqual([{ status: 'student_viewed_feedback' }]);
  });
});
