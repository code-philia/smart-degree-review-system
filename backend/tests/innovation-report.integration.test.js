import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');

const REQ_ID = 'FEAT-INNOVATION-REPORT';
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

async function createCompletedAssessment(username = 'student01', overrides = {}) {
  const cookie = await login(username);
  const payload = assessmentPayload(overrides);
  const response = await request(app)
    .post('/api/normative/innovation-assessments')
    .set('Cookie', cookie)
    .send(payload)
    .expect(201);

  return { cookie, payload, report: response.body };
}

describe('FEAT-INNOVATION-REPORT protected report API and download contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-innovation-report', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-INNOVATION-REPORT:INTEGRATION:AUTHZ:001 denies anonymous report detail and JSON download at the API boundary', async () => {
    const { report } = await createCompletedAssessment('student01');

    await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}`)
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.thesis_title).toBeUndefined();
        expect(body.scoring_snapshot).toBeUndefined();
      });

    await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}/download`)
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.dimensions).toBeUndefined();
      });
  });

  it('FEAT-INNOVATION-REPORT:INTEGRATION:PERMISSION:001 lets student01 read an owned completed assessment as a consistent report DTO', async () => {
    const { cookie, payload, report } = await createCompletedAssessment('student01');

    const response = await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}`)
      .set('Cookie', cookie)
      .expect(200);

    expect(response.body).toMatchObject({
      id: report.id,
      user_id: 'student01',
      thesis_title: payload.thesis_title,
      degree_type: 'master',
      primary_discipline: payload.primary_discipline,
      secondary_discipline: payload.secondary_discipline,
      research_direction: payload.research_direction,
      total_score: report.total_score,
      grade_label: report.grade_label,
      formula: report.formula,
      disclaimer: '本结果为量表自评，不代替专家评审或文献查新',
      input_snapshot: payload,
      scoring_snapshot: report.scoring_snapshot,
    });
    expect(response.body.dimensions).toEqual(response.body.scoring_snapshot.dimensions);
    expect(response.body.input).toEqual(response.body.scoring_snapshot.input);
    expect(response.body.dimensions).toEqual([
      expect.objectContaining({ key: 'research_topic', label: '研究选题', level: 5, weight: 0.2, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_method', label: '研究方法', level: 4, weight: 0.2, weighted_score: 16 }),
      expect.objectContaining({ key: 'research_content', label: '研究内容', level: 4, weight: 0.25, weighted_score: 20 }),
      expect.objectContaining({ key: 'research_conclusion', label: '研究结论', level: 3, weight: 0.2, weighted_score: 12 }),
      expect.objectContaining({ key: 'application_value', label: '应用价值', level: 4, weight: 0.15, weighted_score: 12 }),
    ]);
  });

  it('FEAT-INNOVATION-REPORT:INTEGRATION:AUTHZ:002 hides another authenticated user owned report behind a not-found response', async () => {
    const { report } = await createCompletedAssessment('student01', {
      thesis_title: 'student01 专属创新性报告',
    });
    const supervisorCookie = await login('supervisor01');

    await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}`)
      .set('Cookie', supervisorCookie)
      .expect(404)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 404 });
        expect(body.user_id).toBeUndefined();
        expect(body.scoring_snapshot).toBeUndefined();
      });
  });

  it('FEAT-INNOVATION-REPORT:INTEGRATION:DOWNLOAD:001 downloads UTF-8 JSON derived from the same fetched report values', async () => {
    const { cookie, report } = await createCompletedAssessment('student01');

    const detailResponse = await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}`)
      .set('Cookie', cookie)
      .expect(200);

    const downloadResponse = await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}/download`)
      .set('Cookie', cookie)
      .expect(200);

    expect(downloadResponse.headers['content-type']).toContain('application/json');
    expect(downloadResponse.headers['content-disposition']).toContain(`innovation-report-${report.id}.json`);
    const payload = JSON.parse(downloadResponse.text);
    expect(payload).toMatchObject({
      id: detailResponse.body.id,
      thesis_title: detailResponse.body.thesis_title,
      total_score: detailResponse.body.total_score,
      grade_label: detailResponse.body.grade_label,
      formula: detailResponse.body.formula,
      disclaimer: detailResponse.body.disclaimer,
      input_snapshot: detailResponse.body.input_snapshot,
      scoring_snapshot: detailResponse.body.scoring_snapshot,
      exported_at: expect.any(String),
    });
    expect(payload.dimensions).toEqual(detailResponse.body.dimensions);
    expect(payload.scoring_snapshot.dimensions).toEqual(detailResponse.body.dimensions);
  });

  it('FEAT-INNOVATION-REPORT:INTEGRATION:PERMISSION:002 rejects an authenticated role outside the declared report roles before returning data', async () => {
    const { report } = await createCompletedAssessment('student01');
    await run(
      `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
       SELECT 'guest01', 'guest01', password_hash, 'GUEST', college_id, supervisor_id, scope
       FROM auth_users WHERE username = 'student01';`,
    );
    const guestCookie = await login('guest01');

    await request(app)
      .get(`/api/normative/innovation-assessments/${report.id}`)
      .set('Cookie', guestCookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.thesis_title).toBeUndefined();
      });
  });
});
