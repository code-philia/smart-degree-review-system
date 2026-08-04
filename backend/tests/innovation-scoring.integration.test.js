import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');

const REQ_ID = 'FEAT-INNOVATION-SCORING-MODEL';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

const scenarioPayload = {
  degree_type: 'master',
  levels: {
    research_topic: 5,
    research_method: 4,
    research_content: 4,
    research_conclusion: 3,
    application_value: 4,
  },
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

describe('FEAT-INNOVATION-SCORING-MODEL protected API contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-innovation-scoring-model', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('denies anonymous scoring requests before returning calculation data', async () => {
    await request(app)
      .post('/api/normative/innovation-scores')
      .send(scenarioPayload)
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.total_score).toBeUndefined();
        expect(body.dimensions).toBeUndefined();
      });
  });

  it('allows every declared role to calculate innovation scores through the mounted route', async () => {
    const usernames = ['student01', 'supervisor01', 'school_admin01', 'college_admin01'];

    for (const username of usernames) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/innovation-scores')
        .set('Cookie', cookie)
        .send(scenarioPayload)
        .expect(201)
        .expect(({ body }) => {
          expect(body).toMatchObject({
            degree_type: 'master',
            total_score: 80,
            grade_label: '良好',
            input: scenarioPayload,
          });
          expect(body.formula).toEqual(expect.stringContaining('综合分=各维度原始分×权重之和'));
          expect(body.dimensions).toEqual([
            expect.objectContaining({ key: 'research_topic', level: 5, raw_score: 100, weight: 0.2, weighted_score: 20 }),
            expect.objectContaining({ key: 'research_method', level: 4, raw_score: 80, weight: 0.2, weighted_score: 16 }),
            expect.objectContaining({ key: 'research_content', level: 4, raw_score: 80, weight: 0.25, weighted_score: 20 }),
            expect.objectContaining({ key: 'research_conclusion', level: 3, raw_score: 60, weight: 0.2, weighted_score: 12 }),
            expect.objectContaining({ key: 'application_value', level: 4, raw_score: 80, weight: 0.15, weighted_score: 12 }),
          ]);
        });
    }
  });

  it('rejects invalid scoring payloads with 400 at the HTTP boundary', async () => {
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/innovation-scores')
      .set('Cookie', cookie)
      .send({
        degree_type: 'master',
        levels: {
          research_topic: 5,
          research_method: 4,
          research_content: 4,
          research_conclusion: 3,
          application_value: 9,
        },
      })
      .expect(400)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 400 });
        expect(body.total_score).toBeUndefined();
      });
  });
});
