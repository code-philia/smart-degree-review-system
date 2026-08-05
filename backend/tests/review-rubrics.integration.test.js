import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');

const REQ_ID = 'FEAT-AI-REVIEW-RUBRICS';
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

function expectRubricResponse(body) {
  expect(body.templates.map((template) => template.name)).toEqual([
    '学术型博士自然科学',
    '学术型博士人文社科',
    '专业型博士',
    '学术型硕士',
    '专业型硕士',
  ]);
  expect(body.templates).toHaveLength(5);
  for (const template of body.templates) {
    expect(template.required_sections.length).toBeGreaterThan(0);
    expect(template.minimum_reference_count).toEqual(expect.any(Number));
  }
  expect(body.shared_score_items.map((item) => item.points)).toEqual([30, 20, 20, 20, 10]);
  expect(body.shared_score_items.reduce((total, item) => total + item.points, 0)).toBe(100);
  expect(body.passing_rule).toMatchObject({
    minimum_objective_score: 80,
    no_required_section_missing: true,
    pass_label: '基础检查通过',
    revise_label: '需修改',
  });
}

describe('FEAT-AI-REVIEW-RUBRICS protected API contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ai-review-rubrics', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('denies anonymous requests before returning built-in rubric data', async () => {
    await request(app)
      .get('/api/normative/review-rubrics')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.templates).toBeUndefined();
        expect(body.shared_score_items).toBeUndefined();
      });
  });

  it('allows every declared role to fetch the shared rubric catalog through the mounted normative route', async () => {
    const usernames = ['student01', 'supervisor01', 'school_admin01', 'college_admin01'];

    for (const username of usernames) {
      const cookie = await login(username);
      await request(app)
        .get('/api/normative/review-rubrics')
        .set('Cookie', cookie)
        .expect(200)
        .expect(({ body }) => expectRubricResponse(body));
    }
  });
});
