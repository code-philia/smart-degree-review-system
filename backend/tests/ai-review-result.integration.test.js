import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');

const REQ_ID = 'FEAT-AI-REVIEW-RESULT';
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

function buildReferenceLines(count) {
  return Array.from({ length: count }, (_, index) => `[${index + 1}] 引用条目 ${index + 1}`).join('\n');
}

function completedReviewText(referenceCount = 50) {
  return [
    '摘要',
    '关键词',
    '引言',
    '研究方法',
    '分析与讨论',
    '结论',
    '参考文献',
    buildReferenceLines(referenceCount),
  ].join('\n');
}

async function createCompletedReviewRun(username = 'student01', overrides = {}) {
  const cookie = await login(username);
  const payload = {
    thesis_title: '辅助评阅结果验证论文',
    template_id: 'academic_master',
    text: completedReviewText(),
    source_type: 'paste',
    ...overrides,
  };

  const response = await request(app)
    .post('/api/normative/ai-review-runs')
    .set('Cookie', cookie)
    .send(payload)
    .expect(201);

  return { cookie, payload, run: response.body };
}

describe('FEAT-AI-REVIEW-RESULT protected result API and download contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ai-review-result-api', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-AI-REVIEW-RESULT:INTEGRATION:AUTHZ:001 denies anonymous result detail and JSON download at the API boundary', async () => {
    const { run } = await createCompletedReviewRun('student01');

    await request(app)
      .get(`/api/normative/ai-review-runs/${run.id}`)
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.thesis_title).toBeUndefined();
        expect(body.score_items).toBeUndefined();
      });

    await request(app)
      .get(`/api/normative/ai-review-runs/${run.id}/download`)
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.result).toBeUndefined();
      });
  });

  it('FEAT-AI-REVIEW-RESULT:INTEGRATION:SCENARIO:001 lets a student read an owned completed result with five scores summing to total and all subjective dimensions pending', async () => {
    const { cookie, payload, run } = await createCompletedReviewRun('student01');

    const response = await request(app)
      .get(`/api/normative/ai-review-runs/${run.id}`)
      .set('Cookie', cookie)
      .expect(200);

    expect(response.body).toMatchObject({
      id: run.id,
      user_id: 'student01',
      thesis_title: payload.thesis_title,
      template_id: payload.template_id,
      source_type: 'paste',
      source_filename: null,
      original_text: payload.text,
      total_score: run.total_score,
      result_label: run.result_label,
      normative_issues: run.normative_issues,
      created_at: expect.any(String),
    });
    expect(response.body.score_items).toHaveLength(5);
    expect(response.body.objective_score_total).toBe(
      response.body.score_items.reduce((sum, item) => sum + Number(item.score), 0),
    );
    expect(response.body.objective_score_total).toBe(response.body.total_score);
    expect(response.body.subjective_confirmation_items.length).toBeGreaterThan(0);
    expect(response.body.subjective_confirmation_items.every((item) => item.status === '待人工确认')).toBe(true);
  });

  it('FEAT-AI-REVIEW-RESULT:INTEGRATION:AUTHZ:002 hides another authenticated user owned result behind a not-found response', async () => {
    const { run } = await createCompletedReviewRun('student01', {
      thesis_title: 'student01 专属辅助评阅结果',
    });
    const supervisorCookie = await login('supervisor01');

    await request(app)
      .get(`/api/normative/ai-review-runs/${run.id}`)
      .set('Cookie', supervisorCookie)
      .expect(404)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 404 });
        expect(body.thesis_title).toBeUndefined();
        expect(body.score_items).toBeUndefined();
      });
  });

  it('FEAT-AI-REVIEW-RESULT:INTEGRATION:DOWNLOAD:001 downloads UTF-8 JSON derived from the same fetched result values', async () => {
    const { cookie, run } = await createCompletedReviewRun('student01');

    const detailResponse = await request(app)
      .get(`/api/normative/ai-review-runs/${run.id}`)
      .set('Cookie', cookie)
      .expect(200);

    const downloadResponse = await request(app)
      .get(`/api/normative/ai-review-runs/${run.id}/download`)
      .set('Cookie', cookie)
      .expect(200);

    expect(downloadResponse.headers['content-type']).toContain('application/json');
    expect(downloadResponse.headers['content-disposition']).toContain(`ai-review-result-${run.id}.json`);
    const payload = JSON.parse(downloadResponse.text);
    expect(payload).toMatchObject({
      report_type: 'ai_review_result',
      generated_at: expect.any(String),
      result: detailResponse.body,
    });
    expect(payload.result.score_items).toHaveLength(5);
    expect(payload.result.objective_score_total).toBe(detailResponse.body.total_score);
    expect(payload.result.subjective_confirmation_items.every((item) => item.status === '待人工确认')).toBe(true);
  });
});
