import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get } = require('../src/database');

const REQ_ID = 'FEAT-INNOVATION-ANALYZE';
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

function longText(label) {
  return `${label}证据围绕论文创新点、资料来源和可验证路径展开，明确超过二十个字符。`;
}

function assessmentPayload(overrides = {}) {
  const payload = {
    thesis_title: '高校数字治理创新机制研究',
    degree_type: 'master',
    primary_discipline: '管理学',
    secondary_discipline: '公共管理',
    research_direction: '高校数字治理',
    dimensions: {
      research_topic: {
        level: 5,
        evidence: longText('研究选题'),
        improvement_plan: '研究选题改进计划将补充前沿文献和政策场景，增强问题意识。',
      },
      research_method: {
        level: 4,
        evidence: longText('研究方法'),
        improvement_plan: '研究方法改进计划将增加访谈样本和三角验证，提升方法可靠性。',
      },
      research_content: {
        level: 4,
        evidence: longText('研究内容'),
        improvement_plan: '研究内容改进计划将扩展案例比较和数据解释，增强论证深度。',
      },
      research_conclusion: {
        level: 3,
        evidence: longText('研究结论'),
        improvement_plan: '研究结论改进计划将明确适用边界和进一步研究方向，减少泛化。',
      },
      application_value: {
        level: 4,
        evidence: longText('应用价值'),
        improvement_plan: '应用价值改进计划将设计落地指标和推广条件，提升实践可用性。',
      },
    },
  };

  return {
    ...payload,
    ...overrides,
    dimensions: {
      ...payload.dimensions,
      ...(overrides.dimensions || {}),
    },
  };
}

async function snapshotCount() {
  const row = await get('SELECT COUNT(*) AS count FROM innovation_assessment_snapshots;');
  return row.count;
}

describe('FEAT-INNOVATION-ANALYZE protected API and persistence contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-innovation-assessment', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-INNOVATION-ANALYZE:INTEGRATION:AUTHZ:001 denies anonymous assessment creation before saving snapshots', async () => {
    const before = await snapshotCount();

    await request(app)
      .post('/api/normative/innovation-assessments')
      .send(assessmentPayload())
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.id).toBeUndefined();
        expect(body.scoring_snapshot).toBeUndefined();
      });

    expect(await snapshotCount()).toBe(before);
  });

  it('FEAT-INNOVATION-ANALYZE:INTEGRATION:SCENARIO:001 allows student01 to save input, weights, sub-scores, total score, and grade', async () => {
    const cookie = await login('student01');
    const payload = assessmentPayload();

    const response = await request(app)
      .post('/api/normative/innovation-assessments')
      .set('Cookie', cookie)
      .send(payload)
      .expect(201);

    expect(response.body).toMatchObject({
      id: expect.any(String),
      user_id: 'student01',
      thesis_title: payload.thesis_title,
      degree_type: 'master',
      total_score: 80,
      grade_label: '良好',
      disclaimer: '本结果为量表自评，不代替专家评审或文献查新',
      input_snapshot: payload,
      scoring_snapshot: {
        total_score: 80,
        grade_label: '良好',
        input: {
          degree_type: 'master',
          levels: {
            research_topic: 5,
            research_method: 4,
            research_content: 4,
            research_conclusion: 3,
            application_value: 4,
          },
        },
      },
    });
    expect(response.body.scoring_snapshot.dimensions).toEqual([
      expect.objectContaining({ key: 'research_topic', weight: 0.2, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_method', weight: 0.2, weighted_score: 16 }),
      expect.objectContaining({ key: 'research_content', weight: 0.25, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_conclusion', weight: 0.2, weighted_score: 12 }),
      expect.objectContaining({ key: 'application_value', weight: 0.15, weighted_score: 12 }),
    ]);

    const row = await get('SELECT * FROM innovation_assessment_snapshots WHERE id = ?;', [response.body.id]);
    expect(row).toMatchObject({
      id: response.body.id,
      user_id: 'student01',
      thesis_title: payload.thesis_title,
      degree_type: 'master',
    });
    expect(JSON.parse(row.input_snapshot_json).dimensions.research_method.improvement_plan).toContain('三角验证');
    expect(JSON.parse(row.scoring_snapshot_json)).toMatchObject({ total_score: 80, grade_label: '良好' });
  });

  it('FEAT-INNOVATION-ANALYZE:INTEGRATION:PERMISSION:001 allows every declared authenticated role to create an owned snapshot', async () => {
    const usernames = ['student01', 'supervisor01', 'school_admin01', 'college_admin01'];

    for (const username of usernames) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/innovation-assessments')
        .set('Cookie', cookie)
        .send(assessmentPayload({ thesis_title: `${username} 创新性量表评估` }))
        .expect(201)
        .expect(({ body }) => {
          expect(body.user_id).toBe(username);
          expect(body.id).toEqual(expect.any(String));
          expect(body.total_score).toBe(80);
        });
    }
  });

  it('FEAT-INNOVATION-ANALYZE:INTEGRATION:SCENARIO:002 returns field errors and does not persist when research method evidence is too short', async () => {
    const cookie = await login('student01');
    const before = await snapshotCount();

    await request(app)
      .post('/api/normative/innovation-assessments')
      .set('Cookie', cookie)
      .send(assessmentPayload({
        dimensions: {
          research_method: {
            level: 4,
            evidence: '证据不足',
            improvement_plan: '研究方法改进计划将补充访谈设计和样本说明，确保可复核。',
          },
        },
      }))
      .expect(400)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 400 });
        expect(body.errors).toEqual([
          expect.objectContaining({
            field: 'dimensions.research_method.evidence',
            message: expect.stringContaining('研究方法证据'),
          }),
        ]);
        expect(body.id).toBeUndefined();
      });

    expect(await snapshotCount()).toBe(before);
  });
});
