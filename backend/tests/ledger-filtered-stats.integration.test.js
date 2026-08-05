import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertAiReviewRun } = require('../src/normative/aiReviewRunRepository');
const { getLedgerFilteredStatsForUser } = require('../src/normative/ledgerRecordsService');

const REQ_ID = 'FEAT-LEDGER-FILTERED-STATS';
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

function normIssue(ruleId = 'NORM-001') {
  return [{
    rule_id: ruleId,
    category: '标点配对',
    severity: 'high',
    line: 1,
    column: 3,
    excerpt: '问题片段',
    message: '格式问题',
    suggestion: '修订格式',
  }];
}

async function seedNormativeRecord(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-规范检测.txt`,
    original_text: overrides.original_text || '摘要\n正文存在格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: overrides.template_name || '规范检测模板' }],
    issues: overrides.issues || normIssue(),
    severity_counts: overrides.severity_counts || { high: 1, medium: 0, low: 0 },
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

function todayIsoTimestamp() {
  return `${new Date().toISOString().slice(0, 10)}T09:00:00.000Z`;
}

describe('FEAT-LEDGER-FILTERED-STATS protected filtered statistics contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ledger-filtered-stats', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await harness.reset();
    await seedLedgerUsers();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-LEDGER-FILTERED-STATS:INTEGRATION:AUTHZ:001 denies anonymous and STUDENT callers before statistics are returned', async () => {
    await seedNormativeRecord({ id: 'ledger-stats-authz-owned', user_id: 'student01' });
    const studentCookie = await login('student01');

    await request(app)
      .get('/api/normative/ledger-records/stats')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.total_records).toBeUndefined();
        expect(body.by_type).toBeUndefined();
      });

    await request(app)
      .get('/api/normative/ledger-records/stats')
      .set('Cookie', studentCookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.total_records).toBeUndefined();
        expect(body.daily_trend).toBeUndefined();
      });
  });

  it('FEAT-LEDGER-FILTERED-STATS:INTEGRATION:SCENARIO:001 aggregates only college01 normative records after type and date filters', async () => {
    await seedNormativeRecord({
      id: 'ledger-stats-college01-norm-aug01',
      user_id: 'student01',
      source_filename: 'college01-规范检测-8月1日.txt',
      created_at: '2026-08-01T08:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'ledger-stats-college01-norm-aug02',
      user_id: 'student02',
      source_filename: 'college01-规范检测-8月2日.txt',
      created_at: '2026-08-02T09:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'ledger-stats-college01-norm-out-of-range',
      user_id: 'student01',
      source_filename: 'college01-规范检测-范围外.txt',
      created_at: '2026-08-05T09:00:00.000Z',
    });
    await seedNormativeRecord({
      id: 'ledger-stats-college02-hidden',
      user_id: 'student03',
      source_filename: 'college02-不应统计规范检测.txt',
      created_at: '2026-08-02T10:00:00.000Z',
    });
    await seedDuplicationRecord({
      id: 'ledger-stats-college01-dup-hidden-by-type',
      user_id: 'student01',
      source_filename: 'college01-不应统计查重检测.txt',
      created_at: '2026-08-02T11:00:00.000Z',
    });
    const collegeAdminCookie = await login('college_admin01');

    const response = await request(app)
      .get('/api/normative/ledger-records/stats')
      .query({ detection_type: 'normative', from: '2026-08-01', to: '2026-08-02', latest_only: 'false' })
      .set('Cookie', collegeAdminCookie)
      .expect(200);

    expect(response.body).toMatchObject({
      total_records: 2,
      total_students: 2,
      today_count: 0,
    });
    expect(response.body.by_type).toEqual([
      expect.objectContaining({ detection_type: 'normative', total_records: 2, total_students: 2 }),
    ]);
    expect(response.body.daily_trend).toEqual([
      expect.objectContaining({ date: '2026-08-01', total_records: 1, total_students: 1 }),
      expect.objectContaining({ date: '2026-08-02', total_records: 1, total_students: 1 }),
    ]);
    expect(JSON.stringify(response.body)).not.toContain('college02-不应统计规范检测');
    expect(JSON.stringify(response.body)).not.toContain('college01-不应统计查重检测');
    expect(JSON.stringify(response.body)).not.toContain('范围外');
  });

  it('FEAT-LEDGER-FILTERED-STATS:INTEGRATION:SCOPE:001 allows each permitted role while preserving supervisor and school scopes', async () => {
    await seedNormativeRecord({ id: 'ledger-stats-supervisor01-owned', user_id: 'student01', created_at: todayIsoTimestamp() });
    await seedNormativeRecord({ id: 'ledger-stats-supervisor02-owned', user_id: 'student02', created_at: todayIsoTimestamp() });
    await seedAiReviewRecord({ id: 'ledger-stats-college02-ai-review', user_id: 'student03', created_at: '2026-08-03T11:30:00.000Z' });
    const supervisorCookie = await login('supervisor01');
    const collegeAdminCookie = await login('college_admin01');
    const schoolAdminCookie = await login('school_admin01');

    const supervisorResponse = await request(app)
      .get('/api/normative/ledger-records/stats')
      .query({ detection_type: 'normative' })
      .set('Cookie', supervisorCookie)
      .expect(200);
    expect(supervisorResponse.body).toMatchObject({ total_records: 1, total_students: 1, today_count: 1 });

    const collegeResponse = await request(app)
      .get('/api/normative/ledger-records/stats')
      .query({ detection_type: 'normative' })
      .set('Cookie', collegeAdminCookie)
      .expect(200);
    expect(collegeResponse.body).toMatchObject({ total_records: 2, total_students: 2, today_count: 2 });

    const schoolResponse = await request(app)
      .get('/api/normative/ledger-records/stats')
      .set('Cookie', schoolAdminCookie)
      .expect(200);
    expect(schoolResponse.body.total_records).toBe(3);
    expect(schoolResponse.body.by_type.map((typeStat) => typeStat.detection_type).sort()).toEqual(['ai_review', 'normative']);
  });

  it('FEAT-LEDGER-FILTERED-STATS:FUNC:001 normalizes filters before repository aggregation and rejects unsupported service users', async () => {
    await seedNormativeRecord({ id: 'ledger-stats-service-filter-trimmed', user_id: 'student01', created_at: '2026-08-04T08:00:00.000Z' });
    await seedNormativeRecord({ id: 'ledger-stats-service-filter-other-student', user_id: 'student02', created_at: '2026-08-04T09:00:00.000Z' });

    await expect(getLedgerFilteredStatsForUser(null, {})).rejects.toMatchObject({ status: 401 });
    await expect(getLedgerFilteredStatsForUser({ id: 'student01', role: 'STUDENT' }, {})).rejects.toMatchObject({ status: 403 });

    const stats = await getLedgerFilteredStatsForUser(
      { id: 'college_admin01', role: 'COLLEGE_ADMIN', college_id: 'college01' },
      { student: ' student01 ', detection_type: ' normative ', from: ' 2026-08-04 ', to: ' 2026-08-04 ', latest_only: 'false' },
    );

    expect(stats).toMatchObject({ total_records: 1, total_students: 1 });
    expect(stats.by_type).toEqual([
      expect.objectContaining({ detection_type: 'normative', total_records: 1 }),
    ]);
    expect(stats.daily_trend).toEqual([
      expect.objectContaining({ date: '2026-08-04', total_records: 1, total_students: 1 }),
    ]);
  });
});
