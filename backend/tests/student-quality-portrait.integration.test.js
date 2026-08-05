import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertInnovationAssessmentSnapshot } = require('../src/normative/innovationAssessmentRepository');
const { insertAiReviewRun } = require('../src/normative/aiReviewRunRepository');
const studentQualityPortraitRepository = require('../src/normative/studentQualityPortraitRepository');

const REQ_ID = 'FEAT-STUDENT-QUALITY-PORTRAIT';
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

async function seedScopedUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor02', 'COLLEGE'
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
    status: overrides.status || 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-规范检测.txt`,
    original_text: '摘要\n正文存在格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: [],
    severity_counts: overrides.severity_counts || { high: 2, medium: 0, low: 0 },
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
    total_similarity_rate: overrides.total_similarity_rate ?? 0.1,
    writing_risk_score: 66,
    sample_count: 3,
    report_json: { status: 'completed', top_matches: [] },
    created_at: overrides.created_at || '2026-08-04T10:30:00.000Z',
  });
}

async function seedInnovationRecord(overrides = {}) {
  return insertInnovationAssessmentSnapshot({
    id: overrides.id || `${overrides.user_id || 'student01'}-innovation-portrait`,
    user_id: overrides.user_id || 'student01',
    thesis_title: overrides.thesis_title || '单学生质量画像创新性论文',
    degree_type: 'master',
    primary_discipline: '计算机科学与技术',
    secondary_discipline: '软件工程',
    research_direction: '教育质量分析',
    input_snapshot: { thesis_title: overrides.thesis_title || '单学生质量画像创新性论文' },
    scoring_snapshot: {
      total_score: overrides.total_score ?? 70,
      grade_label: '合格',
      formula: '综合量表分',
      dimensions: [],
      input: {},
    },
    created_at: overrides.created_at || '2026-08-04T11:00:00.000Z',
  });
}

async function seedAiReviewRecord(overrides = {}) {
  return insertAiReviewRun({
    id: overrides.id || `${overrides.user_id || 'student01'}-review-portrait`,
    user_id: overrides.user_id || 'student01',
    thesis_title: overrides.thesis_title || '单学生质量画像 AI 评阅论文',
    template_id: 'academic_master',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-AI评阅.txt`,
    original_text: '摘要\n关键词\n正文\n结论\n参考文献',
    section_snapshot: [],
    reference_count: 12,
    character_count: 120,
    normative_issues: [],
    score_items: overrides.score_items || [],
    total_score: overrides.total_score ?? 80,
    result_label: '基础检查通过',
    missing_sections: [],
    rubric_snapshot: { template: { template_id: 'academic_master', name: '学术型硕士' } },
    created_at: overrides.created_at || '2026-08-04T11:30:00.000Z',
  });
}

describe('FEAT-STUDENT-QUALITY-PORTRAIT protected backend portrait contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-student-quality-portrait', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedScopedUsers();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:INTEGRATION:AUTHZ:001 enforces anonymous, student-owned, and allowed organization-scoped access at the API boundary', async () => {
    await seedNormativeRecord({ id: 'student-quality-portrait-authz-student01', user_id: 'student01' });
    const studentCookie = await login('student01');
    const supervisorCookie = await login('supervisor01');
    const collegeAdminCookie = await login('college_admin01');
    const schoolAdminCookie = await login('school_admin01');

    await request(app)
      .get('/api/normative/ledger-records/student-quality-portrait/student01')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.metrics).toBeUndefined();
      });

    await request(app)
      .get('/api/normative/ledger-records/student-quality-portrait/student02')
      .set('Cookie', studentCookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.metrics).toBeUndefined();
      });

    for (const cookie of [studentCookie, supervisorCookie, collegeAdminCookie, schoolAdminCookie]) {
      await request(app)
        .get('/api/normative/ledger-records/student-quality-portrait/student01')
        .set('Cookie', cookie)
        .expect(200)
        .expect(({ body }) => {
          expect(body.student.student_id).toBe('student01');
          expect(body).toHaveProperty('metrics');
          expect(body).not.toHaveProperty('code', 501);
        });
    }
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:INTEGRATION:SCENARIO:001 returns the latest completed four source scores and computes an equal-weight 80 overall score', async () => {
    await seedNormativeRecord({
      id: 'student-quality-portrait-normative-old',
      user_id: 'student01',
      severity_counts: { high: 5, medium: 0, low: 0 },
      created_at: '2026-08-03T08:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'student-quality-portrait-normative-latest',
      user_id: 'student01',
      severity_counts: { high: 2, medium: 0, low: 0 },
      created_at: '2026-08-04T10:00:00.000Z',
    });
    await seedDuplicationRecord({
      id: 'student-quality-portrait-duplication-latest',
      user_id: 'student01',
      total_similarity_rate: 0.1,
      created_at: '2026-08-04T10:30:00.000Z',
    });
    await seedInnovationRecord({
      id: 'student-quality-portrait-innovation-latest',
      user_id: 'student01',
      total_score: 70,
      created_at: '2026-08-04T11:00:00.000Z',
    });
    await seedAiReviewRecord({
      id: 'student-quality-portrait-review-latest',
      user_id: 'student01',
      total_score: 80,
      created_at: '2026-08-04T11:30:00.000Z',
    });

    const studentCookie = await login('student01');
    const response = await request(app)
      .get('/api/normative/ledger-records/student-quality-portrait/student01')
      .set('Cookie', studentCookie)
      .expect(200);

    expect(response.body.student).toMatchObject({ student_id: 'student01', student_number: 'student01' });
    expect(response.body.completeness).toMatchObject({ complete: true, missing_metric_keys: [], missing_metric_labels: [] });
    expect(response.body.overall_score).toBe(80);
    expect(response.body.metrics).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'normative', score: 80, source_record_id: 'student-quality-portrait-normative-latest', source_created_at: '2026-08-04T10:00:00.000Z' }),
      expect.objectContaining({ key: 'originality', score: 90, source_record_id: 'student-quality-portrait-duplication-latest', source_created_at: '2026-08-04T10:30:00.000Z' }),
      expect.objectContaining({ key: 'innovation', score: 70, source_record_id: 'student-quality-portrait-innovation-latest', source_created_at: '2026-08-04T11:00:00.000Z' }),
      expect.objectContaining({ key: 'review_base', score: 80, source_record_id: 'student-quality-portrait-review-latest', source_created_at: '2026-08-04T11:30:00.000Z' }),
    ]));
    for (const metric of response.body.metrics) {
      expect(metric.detail_url).toMatch(/^\//);
      expect(metric.score).not.toBeNull();
    }
    expect(JSON.stringify(response.body)).not.toContain('student-quality-portrait-normative-old');
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:INTEGRATION:INCOMPLETE:001 preserves null missing metrics and lists missing labels without computing overall score', async () => {
    await seedNormativeRecord({ id: 'student-quality-portrait-incomplete-normative', user_id: 'student01', severity_counts: { high: 2, medium: 0, low: 0 } });
    await seedDuplicationRecord({ id: 'student-quality-portrait-incomplete-duplication', user_id: 'student01', total_similarity_rate: 0.1 });
    await seedInnovationRecord({ id: 'student-quality-portrait-incomplete-innovation', user_id: 'student01', total_score: 70 });

    const studentCookie = await login('student01');
    const response = await request(app)
      .get('/api/normative/ledger-records/student-quality-portrait/student01')
      .set('Cookie', studentCookie)
      .expect(200);

    expect(response.body.overall_score).toBeNull();
    expect(response.body.completeness.complete).toBe(false);
    expect(response.body.completeness.missing_metric_keys).toContain('review_base');
    expect(response.body.completeness.missing_metric_labels).toContain('评阅基础分');
    expect(response.body.metrics).toContainEqual(expect.objectContaining({ key: 'review_base', score: null, source_record_id: null, source_created_at: null, detail_url: null }));
  });

  it('FEAT-STUDENT-QUALITY-PORTRAIT:INTEGRATION:SERVICE:001 denies a student requesting another student before repository access', async () => {
    const repositorySpy = vi.spyOn(studentQualityPortraitRepository, 'getStudentQualityPortrait');
    const studentCookie = await login('student01');

    await request(app)
      .get('/api/normative/ledger-records/student-quality-portrait/student02')
      .set('Cookie', studentCookie)
      .expect(403);

    expect(repositorySpy).not.toHaveBeenCalled();
    repositorySpy.mockRestore();
  });
});
