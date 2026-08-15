import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get } = require('../src/database');
const { seedDemoDatabase } = require('../src/database/seed_demo_db');

const demoPassword = 'ArcDemo123!';
let harness;

function cookieValue(response) {
  return response.headers['set-cookie']?.find((cookie) => cookie.startsWith('arc_session='));
}

async function login(username) {
  const response = await request(app).post('/api/auth/login').send({ username, password: demoPassword }).expect(200);
  return cookieValue(response);
}

describe('explicit demo data seed', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'demo-seed' });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('requires an explicit confirmation flag before writing demo records', async () => {
    await expect(seedDemoDatabase()).rejects.toThrow(/confirmDemoData/);
    await expect(get('SELECT COUNT(*) AS count FROM auth_users')).resolves.toEqual({ count: 0 });
  });

  it('seeds coherent student journeys, scoped management data, and five review workflow rounds idempotently', async () => {
    const first = await seedDemoDatabase({ confirmDemoData: true });
    expect(first.inserted).toBeGreaterThan(0);
    expect(first.updated).toBe(0);
    expect(first.removed).toBe(0);
    expect(first.verification).toEqual({ valid: true, checked: ['student-supervisor', 'submission-report'] });
    expect(first.totals).toMatchObject({
      users: 15,
      normative: 12,
      duplication: 12,
      innovation: 12,
      ai_review: 12,
      whole_polish: 3,
      local_polish: 2,
      corpus: 5,
      submissions: 5,
      todos: 5,
      feedback: 4,
    });

    for (const username of ['student01', 'supervisor01', 'college_admin01', 'school_admin01']) {
      const cookie = await login(username);
      const [normative, duplication, polish, innovation, aiReview] = await Promise.all([
        request(app).get('/api/normative/detection-reports').set('Cookie', cookie).expect(200),
        request(app).get('/api/normative/duplication-detection-reports').set('Cookie', cookie).expect(200),
        request(app).get('/api/normative/polish-history').set('Cookie', cookie).expect(200),
        request(app).get('/api/normative/innovation-assessments').set('Cookie', cookie).expect(200),
        request(app).get('/api/normative/ai-review-runs').set('Cookie', cookie).expect(200),
      ]);
      const expectedHistoryCount = username === 'student01' ? 5 : 0;
      expect(normative.body.records).toHaveLength(expectedHistoryCount);
      expect(duplication.body.records).toHaveLength(expectedHistoryCount);
      expect(polish.body.records).toHaveLength(username === 'student01' ? 5 : 0);
      expect(innovation.body.records).toHaveLength(expectedHistoryCount);
      expect(aiReview.body.records).toHaveLength(expectedHistoryCount);
      expect(normative.body.records.every((record) => !record.source_filename?.includes('[演示]'))).toBe(true);
    }

    const supervisorCookie = await login('supervisor01');
    const queue = await request(app)
      .get('/api/normative/supervisor-review-queue')
      .set('Cookie', supervisorCookie)
      .expect(200);
    expect(queue.body.records).toHaveLength(5);
    expect(queue.body.unread_count).toBe(1);
    expect(queue.body.records.map((record) => record.todo_status)).toEqual(expect.arrayContaining(['pending', 'done']));

    const pendingDetail = await request(app)
      .get('/api/normative/supervisor-review-queue/demo-submission-pending')
      .set('Cookie', supervisorCookie)
      .expect(200);
    expect(pendingDetail.body.report.original_text).toContain('高校数字治理');
    expect(pendingDetail.body.report.findings).toHaveLength(5);
    expect(pendingDetail.body.report.findings[0]).toMatchObject({
      finding_id: 'finding-norm-001',
    });

    const studentCookie = await login('student01');
    const studentResults = await request(app)
      .get('/api/normative/student-report-results')
      .set('Cookie', studentCookie)
      .expect(200);
    expect(studentResults.body.results).toHaveLength(5);
    expect(studentResults.body.results.map((result) => result.status)).toEqual(
      expect.arrayContaining(['submitted_pending_review', 'review_completed_feedback', 'student_viewed_feedback']),
    );

    const schoolCookie = await login('school_admin01');
    const [ledger, dashboard, corpus] = await Promise.all([
      request(app).get('/api/normative/ledger-records').set('Cookie', schoolCookie).expect(200),
      request(app)
        .get('/api/normative/ledger-records/quality-dashboard?latest_only=true')
        .set('Cookie', schoolCookie)
        .expect(200),
      request(app).get('/api/normative/duplication-corpus').set('Cookie', schoolCookie).expect(200),
    ]);
    expect(ledger.body.records).toHaveLength(36);
    expect(new Set(ledger.body.records.map((record) => record.student_id))).toEqual(
      new Set(['student01', 'student02', 'student03', 'student04', 'student05', 'student06', 'student07', 'student08']),
    );
    expect(dashboard.body.sample_count).toBe(8);
    expect(dashboard.body.metrics.every((metric) => metric.sample_count === 8)).toBe(true);
    expect(corpus.body.samples).toHaveLength(5);

    await expect(
      get(
        `SELECT COUNT(*) AS count
           FROM auth_users student
           LEFT JOIN auth_users supervisor ON supervisor.id = student.supervisor_id AND supervisor.role = 'SUPERVISOR'
          WHERE student.id LIKE 'student%' AND student.role = 'STUDENT' AND supervisor.id IS NULL`,
      ),
    ).resolves.toEqual({ count: 0 });
    await expect(
      get(
        `SELECT COUNT(*) AS count
           FROM report_submissions submission
           JOIN normative_detection_tasks report ON report.id = submission.report_id
          WHERE submission.id LIKE 'demo-submission-%' AND report.user_id != submission.student_id`,
      ),
    ).resolves.toEqual({ count: 0 });
    await expect(get("SELECT version FROM demo_seed_metadata WHERE demo_key = 'presentation-full'"))
      .resolves.toMatchObject({ version: first.version });

    const second = await seedDemoDatabase({ confirmDemoData: true });
    expect(second.inserted).toBe(0);
    expect(second.updated).toBe(0);
    expect(second.removed).toBe(0);
    expect(second.totals).toEqual(first.totals);
  });
});
