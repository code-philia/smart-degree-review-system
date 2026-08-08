import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createCorpusSample } = require('../src/normative/duplicationCorpusRepository');

const REQ_ID = 'FEAT-DUPLICATION-DETECT';
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

function detectionText() {
  return [
    '本文首先分析高校数字治理平台的建设背景。',
    '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
    '因此，本文认为相关单位应当进一步完善制度设计，提升协同治理能力。',
  ].join('\n');
}

async function seedMatchingCorpusSample(overrides = {}) {
  return createCorpusSample({
    id: 'dup-detect-sample-001',
    title: '高校数字治理样本',
    subject: '管理学',
    year: 2024,
    content: [
      '本研究采用问卷调查与访谈相结合的方法，对高校数字治理平台的建设效果进行分析。',
      '平台建设需要兼顾数据共享、流程再造和持续评估。',
    ].join('\n'),
    source_type: 'paste',
    source_filename: null,
    created_by: 'school_admin01',
    created_at: '2024-01-01T00:00:00.000Z',
    ...overrides,
  });
}

function expectRiskReportShape(risk) {
  expect(risk).toMatchObject({
    label: 'heuristic_only',
    explanation: expect.stringMatching(/启发式风险|并非 AI 真伪结论/),
    factors: expect.objectContaining({
      paragraph_duplication_rate: expect.any(Number),
      sentence_length_low_variation: expect.any(Number),
      template_connector_density: expect.any(Number),
      vague_phrase_density: expect.any(Number),
    }),
    weights: {
      paragraph_duplication_rate: 0.35,
      sentence_length_low_variation: 0.25,
      template_connector_density: 0.2,
      vague_phrase_density: 0.2,
    },
  });
  expect(risk.score).toBeGreaterThanOrEqual(0);
  expect(risk.score).toBeLessThanOrEqual(100);
}

describe('FEAT-DUPLICATION-DETECT protected local similarity API contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-duplication-detect', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-DUPLICATION-DETECT:API:AUTHZ:001 denies anonymous requests and allows every declared authenticated role at the backend boundary', async () => {
    await request(app)
      .post('/api/normative/duplication-detections')
      .send({ text: detectionText(), source_type: 'paste' })
      .expect(401);

    await run('DELETE FROM duplication_corpus_samples');

    for (const username of ['student01', 'supervisor01', 'college_admin01', 'school_admin01']) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/duplication-detections')
        .set('Cookie', cookie)
        .send({ text: detectionText(), source_type: 'paste' })
        .expect(201)
        .expect(({ body }) => {
          expect(body.status).toBe('no_samples');
          expect(body.sample_count).toBe(0);
          expect(body.top_matches).toEqual([]);
          expectRiskReportShape(body.risk);
        });
    }
  });

  it('FEAT-DUPLICATION-DETECT:SCENARIO:001 returns top sample, Jaccard score, similar segment, and de-duplicated total similarity rate', async () => {
    await run('DELETE FROM duplication_corpus_samples');
    const sample = await seedMatchingCorpusSample();
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/duplication-detections')
      .set('Cookie', cookie)
      .send({ text: detectionText(), source_type: 'paste' })
      .expect(201)
      .expect(({ body }) => {
        expect(body).toMatchObject({
          status: 'completed',
          source_type: 'paste',
          source_filename: null,
          threshold: 0.65,
          sample_count: 1,
        });
        expect(body.effective_character_count).toBeGreaterThan(0);
        expect(body.total_similarity_rate).toBeGreaterThan(0);
        expect(body.total_similarity_rate).toBeLessThanOrEqual(1);
        expect(body.top_matches).toHaveLength(1);
        expect(body.top_matches[0]).toMatchObject({
          sample_id: sample.id,
          title: sample.title,
          subject: sample.subject,
          year: sample.year,
          jaccard_score: expect.any(Number),
          matched_character_count: expect.any(Number),
        });
        expect(body.top_matches[0].jaccard_score).toBeGreaterThanOrEqual(body.threshold);
        expect(body.top_matches[0].segments.length).toBeGreaterThan(0);
        expect(body.top_matches[0].segments[0]).toMatchObject({
          source_start: expect.any(Number),
          source_end: expect.any(Number),
          sample_start: expect.any(Number),
          sample_end: expect.any(Number),
          source_excerpt: expect.stringContaining('高校数字治理平台的建设效果'),
          sample_excerpt: expect.stringContaining('高校数字治理平台的建设效果'),
        });
        expectRiskReportShape(body.risk);
      });
  });

  it('FEAT-DUPLICATION-DETECT:SCENARIO:002 returns no_samples without fabricated matches while still calculating writing risk', async () => {
    await run('DELETE FROM duplication_corpus_samples');
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/duplication-detections')
      .set('Cookie', cookie)
      .send({ text: detectionText(), source_type: 'paste' })
      .expect(201)
      .expect(({ body }) => {
        expect(body.status).toBe('no_samples');
        expect(body.sample_count).toBe(0);
        expect(body.top_matches).toEqual([]);
        expect(body.effective_character_count).toBeGreaterThan(0);
        expect(body.total_similarity_rate).toBe(0);
        expectRiskReportShape(body.risk);
      });
  });

  it('FEAT-DUPLICATION-DETECT:API:VALIDATION:001 rejects blank and oversized submitted text before returning detection reports', async () => {
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/duplication-detections')
      .set('Cookie', cookie)
      .send({ text: '   ', source_type: 'paste' })
      .expect(400)
      .expect(({ body }) => {
        expect(body.message).toMatch(/待检文本不能为空/);
      });

    await run('DELETE FROM duplication_corpus_samples');

    await request(app)
      .post('/api/normative/duplication-detections')
      .set('Cookie', cookie)
      .send({ text: 'a'.repeat(128 * 1024), source_type: 'paste' })
      .expect(201)
      .expect(({ body }) => {
        expect(body.status).toBe('no_samples');
        expect(body.effective_character_count).toBe(128 * 1024);
      });

    await request(app)
      .post('/api/normative/duplication-detections')
      .set('Cookie', cookie)
      .set('Content-Type', 'application/json')
      .set('Content-Length', String(100 * 1024 * 1024 + 64 * 1024 + 1))
      .send('{}')
      .expect(413)
      .expect(({ body }) => {
        expect(body.message).toMatch(/50 MB|超过|过大/);
      });
  });
});
