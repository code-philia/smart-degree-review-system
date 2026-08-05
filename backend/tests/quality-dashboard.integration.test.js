import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertInnovationAssessmentSnapshot } = require('../src/normative/innovationAssessmentRepository');

const REQ_ID = 'FEAT-QUALITY-DASHBOARD';
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

async function seedQualityDashboardUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor02', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student03', 'student03', password_hash, 'STUDENT', 'college02', 'supervisor03', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'supervisor02', 'supervisor02', password_hash, 'SUPERVISOR', 'college01', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
}

async function seedNormativeRecord(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-规范检测.txt`,
    original_text: overrides.original_text || '摘要\n正文存在格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: overrides.issues || [
      { rule_id: 'NORM-001', category: '结构', severity: 'high', line: 1, column: 1, excerpt: '严重', message: '严重错误', suggestion: '修改' },
      { rule_id: 'NORM-002', category: '格式', severity: 'medium', line: 2, column: 1, excerpt: '一般', message: '一般错误', suggestion: '修改' },
      { rule_id: 'NORM-003', category: '标点', severity: 'low', line: 3, column: 1, excerpt: '轻微', message: '轻微错误', suggestion: '修改' },
    ],
    severity_counts: overrides.severity_counts || { high: 1, medium: 2, low: 3 },
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  });
}

async function seedDuplicationRecord(overrides = {}) {
  return createDuplicationHistoryRecord({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-查重检测.txt`,
    original_text: '查重原文内容',
    total_similarity_rate: overrides.total_similarity_rate ?? 0.27,
    writing_risk_score: overrides.writing_risk_score ?? 66,
    sample_count: overrides.sample_count ?? 3,
    report_json: { status: 'completed', top_matches: [] },
    created_at: overrides.created_at || '2026-08-04T10:30:00.000Z',
  });
}

async function seedInnovationRecord(overrides = {}) {
  return insertInnovationAssessmentSnapshot({
    id: overrides.id || `${overrides.user_id || 'student01'}-innovation-quality`,
    user_id: overrides.user_id || 'student01',
    thesis_title: overrides.thesis_title || '质量仪表盘创新性论文',
    degree_type: 'master',
    primary_discipline: '计算机科学与技术',
    secondary_discipline: '软件工程',
    research_direction: '教育质量分析',
    input_snapshot: { thesis_title: overrides.thesis_title || '质量仪表盘创新性论文' },
    scoring_snapshot: {
      total_score: overrides.total_score ?? 88,
      grade_label: '优秀',
      formula: '综合量表分',
      dimensions: [],
      input: {},
    },
    created_at: overrides.created_at || '2026-08-04T11:00:00.000Z',
  });
}

function metricByKey(body, key) {
  return body.metrics.find((metric) => metric.key === key);
}

function studentById(body, studentId) {
  return body.students.find((student) => student.student_id === studentId);
}

describe('FEAT-QUALITY-DASHBOARD protected quality dashboard contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-quality-dashboard', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedQualityDashboardUsers();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-QUALITY-DASHBOARD:INTEGRATION:AUTHZ:001 enforces anonymous, denied-role, and allowed-role access at the backend boundary', async () => {
    await seedNormativeRecord({ id: 'quality-dashboard-authz-owned', user_id: 'student01' });
    const studentCookie = await login('student01');
    const supervisorCookie = await login('supervisor01');
    const collegeAdminCookie = await login('college_admin01');
    const schoolAdminCookie = await login('school_admin01');

    await request(app)
      .get('/api/normative/ledger-records/quality-dashboard')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.metrics).toBeUndefined();
      });

    await request(app)
      .get('/api/normative/ledger-records/quality-dashboard')
      .set('Cookie', studentCookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.students).toBeUndefined();
      });

    for (const cookie of [supervisorCookie, collegeAdminCookie, schoolAdminCookie]) {
      await request(app)
        .get('/api/normative/ledger-records/quality-dashboard')
        .set('Cookie', cookie)
        .expect(200)
        .expect(({ body }) => {
          expect(body).toHaveProperty('sample_count');
          expect(body).toHaveProperty('metrics');
          expect(body).not.toHaveProperty('code', 501);
        });
    }
  });

  it('FEAT-QUALITY-DASHBOARD:INTEGRATION:SCENARIO:001 aggregates formula scores and excludes missing review base values from averages', async () => {
    await seedNormativeRecord({
      id: 'quality-dashboard-student01-normative',
      user_id: 'student01',
      severity_counts: { high: 1, medium: 2, low: 3 },
      created_at: '2026-08-04T10:00:00.000Z',
    });
    await seedDuplicationRecord({
      id: 'quality-dashboard-student01-duplication',
      user_id: 'student01',
      total_similarity_rate: 0.27,
      created_at: '2026-08-04T10:30:00.000Z',
    });
    await seedInnovationRecord({
      id: 'quality-dashboard-student01-innovation',
      user_id: 'student01',
      total_score: 88,
      created_at: '2026-08-04T11:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'quality-dashboard-student02-normative-other-supervisor',
      user_id: 'student02',
      severity_counts: { high: 0, medium: 0, low: 0 },
      created_at: '2026-08-04T10:00:00.000Z',
    });

    const supervisorCookie = await login('supervisor01');
    const response = await request(app)
      .get('/api/normative/ledger-records/quality-dashboard')
      .query({ from: '2026-08-04', to: '2026-08-04', latest_only: 'false' })
      .set('Cookie', supervisorCookie)
      .expect(200);

    expect(response.body.sample_count).toBe(1);
    expect(metricByKey(response.body, 'normative')).toMatchObject({ average_score: 79, sample_count: 1, missing_count: 0 });
    expect(metricByKey(response.body, 'originality')).toMatchObject({ average_score: 73, sample_count: 1, missing_count: 0 });
    expect(metricByKey(response.body, 'innovation')).toMatchObject({ average_score: 88, sample_count: 1, missing_count: 0 });
    expect(metricByKey(response.body, 'review_base')).toMatchObject({ average_score: null, sample_count: 0, missing_count: 1 });

    expect(studentById(response.body, 'student01')).toMatchObject({
      scores: {
        normative: 79,
        originality: 73,
        innovation: 88,
        review_base: null,
      },
    });
    expect(JSON.stringify(response.body)).not.toContain('student02');
  });

  it('FEAT-QUALITY-DASHBOARD:INTEGRATION:FILTERS:001 applies student, type, and date filters without routing quality-dashboard as a record id', async () => {
    await seedNormativeRecord({
      id: 'quality-dashboard-filter-student01-in-range',
      user_id: 'student01',
      source_filename: '张三-规范检测-范围内.txt',
      severity_counts: { high: 0, medium: 0, low: 5 },
      created_at: '2026-08-05T09:00:00.000Z',
    });
    await seedDuplicationRecord({
      id: 'quality-dashboard-filter-duplication-hidden-by-type',
      user_id: 'student01',
      source_filename: '张三-查重检测-类型过滤.txt',
      total_similarity_rate: 0.5,
      created_at: '2026-08-05T09:30:00.000Z',
    });
    await seedNormativeRecord({
      id: 'quality-dashboard-filter-out-of-range',
      user_id: 'student01',
      source_filename: '张三-规范检测-范围外.txt',
      severity_counts: { high: 5, medium: 0, low: 0 },
      created_at: '2026-08-07T09:00:00.000Z',
    });

    const supervisorCookie = await login('supervisor01');
    const response = await request(app)
      .get('/api/normative/ledger-records/quality-dashboard')
      .query({ student: 'student01', detection_type: 'normative', from: '2026-08-05', to: '2026-08-05', latest_only: 'false' })
      .set('Cookie', supervisorCookie)
      .expect(200);

    expect(response.body.filters).toMatchObject({
      student: 'student01',
      detection_type: 'normative',
      from: '2026-08-05',
      to: '2026-08-05',
      latest_only: false,
    });
    expect(response.body.sample_count).toBe(1);
    expect(metricByKey(response.body, 'normative')).toMatchObject({ average_score: 95 });
    expect(metricByKey(response.body, 'originality')).toMatchObject({ average_score: null, sample_count: 0 });
    expect(JSON.stringify(response.body)).not.toContain('范围外');
  });
});
