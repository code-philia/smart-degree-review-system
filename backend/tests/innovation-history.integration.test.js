import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const {
  ALLOWED_INNOVATION_HISTORY_ROLES,
  listInnovationHistoryForUser,
} = require('../src/normative/innovationHistoryService');
const { listInnovationAssessmentHistoryForUser } = require('../src/normative/innovationAssessmentRepository');

const REQ_ID = 'FEAT-INNOVATION-HISTORY';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

const usersByRole = {
  STUDENT: 'student01',
  SUPERVISOR: 'supervisor01',
  SCHOOL_ADMIN: 'school_admin01',
  COLLEGE_ADMIN: 'college_admin01',
};

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

function scoringSnapshot(overrides = {}) {
  return {
    degree_type: overrides.degree_type || 'master',
    total_score: overrides.total_score ?? 80,
    grade_label: overrides.grade_label || '良好',
    formula: '维度原始分=等级×20；综合分=各维度原始分×权重之和。',
    dimensions: [
      { key: 'research_topic', label: '研究选题', level: 5, weight: 0.2, raw_score: 100, weighted_score: 20 },
      { key: 'research_method', label: '研究方法', level: 4, weight: 0.2, raw_score: 80, weighted_score: 16 },
    ],
    input: {
      degree_type: overrides.degree_type || 'master',
      levels: { research_topic: 5, research_method: 4 },
    },
  };
}

function assessmentRow(overrides = {}) {
  const degreeType = overrides.degree_type || 'master';
  return {
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    thesis_title: overrides.thesis_title || '高校数字治理创新机制研究',
    degree_type: degreeType,
    primary_discipline: overrides.primary_discipline || '管理学',
    secondary_discipline: overrides.secondary_discipline || '公共管理',
    research_direction: overrides.research_direction || '高校数字治理',
    input_snapshot_json: JSON.stringify({
      thesis_title: overrides.thesis_title || '高校数字治理创新机制研究',
      degree_type: degreeType,
      primary_discipline: overrides.primary_discipline || '管理学',
      secondary_discipline: overrides.secondary_discipline || '公共管理',
      research_direction: overrides.research_direction || '高校数字治理',
      dimensions: {},
    }),
    scoring_snapshot_json: JSON.stringify(scoringSnapshot({
      degree_type: degreeType,
      total_score: overrides.total_score,
      grade_label: overrides.grade_label,
    })),
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  };
}

async function seedAssessment(overrides = {}) {
  const row = assessmentRow(overrides);
  await run(
    `INSERT INTO innovation_assessment_snapshots (
      id,
      user_id,
      thesis_title,
      degree_type,
      primary_discipline,
      secondary_discipline,
      research_direction,
      input_snapshot_json,
      scoring_snapshot_json,
      created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);`,
    [
      row.id,
      row.user_id,
      row.thesis_title,
      row.degree_type,
      row.primary_discipline,
      row.secondary_discipline,
      row.research_direction,
      row.input_snapshot_json,
      row.scoring_snapshot_json,
      row.created_at,
    ],
  );
  return row;
}

describe('FEAT-INNOVATION-HISTORY owned history API, service, and repository contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-innovation-history', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM innovation_assessment_snapshots');
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-INNOVATION-HISTORY:API:AUTHZ:001 denies anonymous history listing before returning assessment records', async () => {
    await seedAssessment({ id: 'student01-anonymous-history-boundary' });

    await request(app)
      .get('/api/normative/innovation-assessments')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.records).toBeUndefined();
        expect(body.thesis_title).toBeUndefined();
      });
  });

  it('FEAT-INNOVATION-HISTORY:API:ROLES:001 allows every declared authenticated role at the owned backend boundary', async () => {
    expect(ALLOWED_INNOVATION_HISTORY_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

    for (const [role, username] of Object.entries(usersByRole)) {
      await seedAssessment({
        id: `${username}-innovation-history-role-record`,
        user_id: username,
        thesis_title: `${role} 创新性历史记录`,
        total_score: 76,
        grade_label: '中等',
      });
      const cookie = await login(username);

      await request(app)
        .get('/api/normative/innovation-assessments')
        .set('Cookie', cookie)
        .expect(200)
        .expect(({ body }) => {
          expect(body.records).toEqual(expect.arrayContaining([
            expect.objectContaining({
              id: `${username}-innovation-history-role-record`,
              user_id: username,
              thesis_title: `${role} 创新性历史记录`,
              total_score: 76,
              grade_label: '中等',
            }),
          ]));
        });
    }
  });

  it('FEAT-INNOVATION-HISTORY:SCENARIO:001 lists only student01 assessments in generation-time descending order with history DTO fields', async () => {
    await seedAssessment({
      id: 'student01-innovation-history-old',
      thesis_title: 'student01 第一次创新性评估',
      degree_type: 'master',
      total_score: 72,
      grade_label: '中等',
      created_at: '2026-08-04T09:00:00.000Z',
    });
    await seedAssessment({
      id: 'student01-innovation-history-new',
      thesis_title: 'student01 第二次创新性评估',
      degree_type: 'doctoral',
      total_score: 88,
      grade_label: '优秀',
      created_at: '2026-08-04T11:00:00.000Z',
    });
    await seedAssessment({
      id: 'supervisor-innovation-history-hidden',
      user_id: 'supervisor01',
      thesis_title: 'supervisor 不应出现在学生历史中',
      created_at: '2026-08-04T12:00:00.000Z',
    });
    const cookie = await login('student01');

    await request(app)
      .get('/api/normative/innovation-assessments')
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.records.map((record) => record.id)).toEqual([
          'student01-innovation-history-new',
          'student01-innovation-history-old',
        ]);
        expect(body.records.find((record) => record.id === 'supervisor-innovation-history-hidden')).toBeUndefined();
        expect(body.records[0]).toMatchObject({
          id: 'student01-innovation-history-new',
          user_id: 'student01',
          thesis_title: 'student01 第二次创新性评估',
          degree_type: 'doctoral',
          total_score: 88,
          grade_label: '优秀',
          created_at: '2026-08-04T11:00:00.000Z',
        });
        expect(body.records[0].scoring_snapshot_json).toBeUndefined();
        expect(body.records[0].input_snapshot_json).toBeUndefined();
      });
  });

  it('FEAT-INNOVATION-HISTORY:FUNC:001 rejects missing or unsupported users and never widens repository scope', async () => {
    await seedAssessment({ id: 'student01-service-history', created_at: '2026-08-04T13:00:00.000Z' });
    await seedAssessment({ id: 'supervisor-service-history', user_id: 'supervisor01', created_at: '2026-08-04T14:00:00.000Z' });

    await expect(listInnovationHistoryForUser(null)).rejects.toMatchObject({ status: 401 });
    await expect(listInnovationHistoryForUser({ id: 'guest01', username: 'guest01', role: 'GUEST' }))
      .rejects.toMatchObject({ status: 403 });
    await expect(listInnovationAssessmentHistoryForUser({ id: 'student01' })).resolves.toEqual([
      expect.objectContaining({ id: 'student01-service-history', user_id: 'student01' }),
    ]);
  });
});
