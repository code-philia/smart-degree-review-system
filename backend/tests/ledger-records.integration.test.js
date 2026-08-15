import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertInnovationAssessmentSnapshot } = require('../src/normative/innovationAssessmentRepository');
const { insertAiReviewRun } = require('../src/normative/aiReviewRunRepository');
const {
  buildLedgerAccessScope,
  buildLedgerCsv,
  getLedgerRecordForUser,
  listLedgerRecordsForUser,
} = require('../src/normative/ledgerRecordsService');

const REQ_ID = 'FEAT-LEDGER-RECORDS';
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

async function seedLedgerUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor02', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student03', 'student03', password_hash, 'STUDENT', 'college02', 'supervisor03', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'supervisor02', 'supervisor02', password_hash, 'SUPERVISOR', 'college01', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'college_admin02', 'college_admin02', password_hash, 'COLLEGE_ADMIN', 'college02', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
}

function normIssue(count = 1) {
  return Array.from({ length: count }, (_, index) => ({
    rule_id: `NORM-${index + 1}`,
    category: '标点配对',
    severity: index === 0 ? 'high' : 'medium',
    line: index + 1,
    column: 3,
    excerpt: '问题片段',
    message: '格式问题',
    suggestion: '修订格式',
  }));
}

async function seedNormativeRecord(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-规范检测.txt`,
    original_text: overrides.original_text || '摘要\n正文存在格式问题。',
    rule_snapshot: overrides.rule_snapshot || [{ rule_id: 'NORM-001', title: overrides.template_name || '规范检测模板' }],
    issues: overrides.issues || normIssue(overrides.issue_count || 1),
    severity_counts: overrides.severity_counts || { high: overrides.issue_count || 1, medium: 0, low: 0 },
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
    total_similarity_rate: overrides.total_similarity_rate ?? 0.37,
    writing_risk_score: overrides.writing_risk_score ?? 66,
    sample_count: overrides.sample_count ?? 3,
    report_json: { status: 'completed', top_matches: [] },
    created_at: overrides.created_at || '2026-08-04T10:30:00.000Z',
  });
}

async function seedInnovationRecord(overrides = {}) {
  const snapshot = {
    id: overrides.id || `${overrides.user_id || 'student01'}-innovation-ledger`,
    user_id: overrides.user_id || 'student01',
    thesis_title: overrides.thesis_title || '创新性台账论文',
    degree_type: 'master',
    primary_discipline: '管理学',
    secondary_discipline: '公共管理',
    research_direction: '高校数字治理',
    input_snapshot: { dimensions: {} },
    scoring_snapshot: { total_score: overrides.total_score ?? 82, grade_label: overrides.grade_label || '良好', dimensions: [], formula: 'sum' },
    created_at: overrides.created_at || '2026-08-04T11:00:00.000Z',
  };
  await insertInnovationAssessmentSnapshot(snapshot);
  return snapshot;
}

async function seedAiReviewRecord(overrides = {}) {
  return insertAiReviewRun({
    id: overrides.id || `${overrides.user_id || 'student01'}-ai-review-ledger`,
    user_id: overrides.user_id || 'student01',
    thesis_title: overrides.thesis_title || 'AI评阅台账论文',
    template_id: 'academic_master',
    source_type: 'paste',
    source_filename: null,
    original_text: '摘要\n关键词\n引言\n结论\n参考文献\n[1] 示例',
    section_snapshot: [],
    reference_count: 1,
    character_count: 30,
    normative_issues: [],
    score_items: [],
    total_score: overrides.total_score ?? 91,
    result_label: overrides.result_label || '基础检查通过',
    missing_sections: [],
    rubric_snapshot: {},
    created_at: overrides.created_at || '2026-08-04T11:30:00.000Z',
  });
}

describe('FEAT-LEDGER-RECORDS protected ledger API, service, and repository contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ledger-records', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedLedgerUsers();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-LEDGER-RECORDS:INTEGRATION:AUTHZ:001 denies anonymous and STUDENT callers before ledger data is returned', async () => {
    await seedNormativeRecord({ id: 'ledger-authz-owned', user_id: 'student01' });
    const studentCookie = await login('student01');

    await request(app)
      .get('/api/normative/ledger-records')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.records).toBeUndefined();
      });

    await request(app)
      .get('/api/normative/ledger-records')
      .set('Cookie', studentCookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.records).toBeUndefined();
      });
  });

  it('FEAT-LEDGER-RECORDS:SCENARIO:001 supervisor list and UTF-8 CSV export contain only current supervisor students after filters', async () => {
    const ownedNew = await seedNormativeRecord({
      id: 'ledger-supervisor-owned-new',
      user_id: 'student01',
      source_filename: 'supervisor01-最新规范检测.txt',
      issue_count: 2,
      created_at: '2026-08-05T10:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'ledger-supervisor-owned-old',
      user_id: 'student01',
      source_filename: 'supervisor01-旧规范检测.txt',
      issue_count: 1,
      created_at: '2026-08-04T10:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'ledger-other-supervisor-hidden',
      user_id: 'student02',
      source_filename: 'supervisor02-不应出现规范检测.txt',
      created_at: '2026-08-06T10:00:00.000Z',
    });
    await seedDuplicationRecord({ id: 'ledger-supervisor-owned-dup', user_id: 'student01', created_at: '2026-08-06T11:00:00.000Z' });
    const supervisorCookie = await login('supervisor01');

    const listResponse = await request(app)
      .get('/api/normative/ledger-records')
      .query({ student: 'student01', detection_type: 'normative', from: '2026-08-01', to: '2026-08-31', latest_only: 'true' })
      .set('Cookie', supervisorCookie)
      .expect(200);

    expect(listResponse.body.records).toHaveLength(1);
    expect(listResponse.body.records[0]).toMatchObject({
      id: `normative:${ownedNew.id}`,
      student_id: 'student01',
      supervisor_id: 'supervisor01',
      detection_type: 'normative',
      is_latest: true,
      detail_url: `/normative-reports/${ownedNew.id}`,
    });
    expect(JSON.stringify(listResponse.body.records)).not.toContain('supervisor02-不应出现规范检测');
    expect(JSON.stringify(listResponse.body.records)).not.toContain('查重检测');

    const csvResponse = await request(app)
      .get('/api/normative/ledger-records/export.csv')
      .query({ student: 'student01', detection_type: 'normative', from: '2026-08-01', to: '2026-08-31', latest_only: 'true' })
      .set('Cookie', supervisorCookie)
      .expect(200)
      .expect('content-type', /text\/csv; charset=utf-8/);

    expect(csvResponse.text.charCodeAt(0)).toBe(0xfeff);
    expect(csvResponse.text).toContain('"记录ID","学院","学号","姓名","导师"');
    expect(csvResponse.text).toContain('ledger-supervisor-owned-new');
    expect(csvResponse.text).toContain('student01');
    expect(csvResponse.text).not.toContain('ledger-supervisor-owned-old');
    expect(csvResponse.text).not.toContain('ledger-other-supervisor-hidden');
  });

  it('FEAT-LEDGER-RECORDS:SCENARIO:002 returns 403 for college admin detail access outside college without leaking record content', async () => {
    const outOfScopeRecord = await seedNormativeRecord({
      id: 'ledger-college02-hidden-detail',
      user_id: 'student03',
      source_filename: 'college02-敏感论文记录.txt',
      original_text: 'college02 record secret content should not leak',
      created_at: '2026-08-04T12:00:00.000Z',
    });
    const collegeAdminCookie = await login('college_admin01');

    await request(app)
      .get(`/api/normative/ledger-records/${outOfScopeRecord.id}`)
      .set('Cookie', collegeAdminCookie)
      .expect(403)
      .expect(({ body, text }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(text).not.toContain('college02-敏感论文记录.txt');
        expect(text).not.toContain('college02 record secret content should not leak');
        expect(body.student_name).toBeUndefined();
        expect(body.detail_url).toBeUndefined();
      });
  });

  it('FEAT-LEDGER-RECORDS:INTEGRATION:SCOPE:001 applies college and school admin scopes across all supported ledger types', async () => {
    await seedNormativeRecord({ id: 'ledger-college01-normative', user_id: 'student01', created_at: '2026-08-04T08:00:00.000Z' });
    await seedDuplicationRecord({ id: 'ledger-college01-duplication', user_id: 'student02', created_at: '2026-08-04T09:00:00.000Z' });
    await seedInnovationRecord({ id: 'ledger-college02-innovation', user_id: 'student03', created_at: '2026-08-04T10:00:00.000Z' });
    await seedAiReviewRecord({ id: 'ledger-college01-ai-review', user_id: 'student01', created_at: '2026-08-04T11:00:00.000Z' });
    const collegeCookie = await login('college_admin01');
    const schoolCookie = await login('school_admin01');

    const collegeResponse = await request(app)
      .get('/api/normative/ledger-records')
      .set('Cookie', collegeCookie)
      .expect(200);
    expect(collegeResponse.body.records.map((record) => record.id)).toEqual([
      'ai_review:ledger-college01-ai-review',
      'duplication:ledger-college01-duplication',
      'normative:ledger-college01-normative',
    ]);
    expect(collegeResponse.body.records.map((record) => record.id)).not.toContain('ledger-college02-innovation');

    const schoolResponse = await request(app)
      .get('/api/normative/ledger-records')
      .set('Cookie', schoolCookie)
      .expect(200);
    expect(schoolResponse.body.records.map((record) => record.id)).toEqual([
      'ai_review:ledger-college01-ai-review',
      'duplication:ledger-college01-duplication',
      'normative:ledger-college01-normative',
    ]);
  });

  it('FEAT-LEDGER-RECORDS:FUNC:001 derives role scopes, rejects unsupported users, and escapes CSV cells', async () => {
    expect(buildLedgerAccessScope({ id: 'supervisor01', username: 'supervisor01', role: 'SUPERVISOR' })).toEqual({
      role: 'SUPERVISOR',
      supervisor_id: 'supervisor01',
    });
    expect(buildLedgerAccessScope({ id: 'college_admin01', role: 'COLLEGE_ADMIN', college_id: 'college01' })).toEqual({
      role: 'COLLEGE_ADMIN',
      college_id: 'college01',
    });
    expect(buildLedgerAccessScope({ id: 'school_admin01', role: 'SCHOOL_ADMIN' })).toEqual({ role: 'SCHOOL_ADMIN' });
    expect(() => buildLedgerAccessScope(null)).toThrow('请先登录后查看检测台账');
    expect(() => buildLedgerAccessScope({ id: 'student01', role: 'STUDENT' })).toThrow('当前角色无权查看检测台账');

    const csv = buildLedgerCsv([
      {
        id: 'csv-1',
        college_name: '信息学院',
        student_number: 'S001',
        student_name: '张三',
        supervisor_name: '李"导师',
        student_category: '硕士',
        thesis_title: '包含,逗号的论文',
        detection_type: 'normative',
        template_name: '模板A',
        core_result: '错误数 2',
        detail_url: '/normative-reports/csv-1',
        created_at: '2026-08-04T10:00:00.000Z',
      },
    ]);
    expect(csv).toContain('"李""导师"');
    expect(csv).toContain('"包含,逗号的论文"');

    await expect(listLedgerRecordsForUser(null, {})).rejects.toMatchObject({ status: 401 });
    await expect(getLedgerRecordForUser({ id: 'student01', role: 'STUDENT' }, 'any-id')).rejects.toMatchObject({ status: 403 });
  });
});
