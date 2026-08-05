import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');
const { insertAiReviewRun } = require('../src/normative/aiReviewRunRepository');

const REQ_ID = 'FEAT-AI-REVIEW-HISTORY';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;
let fixtureSequence = 0;

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

function reviewRunFixture(overrides = {}) {
  fixtureSequence += 1;
  return {
    id: `review-history-api-${fixtureSequence}`,
    user_id: 'student01',
    thesis_title: `辅助评阅历史论文 ${fixtureSequence}`,
    template_id: 'academic_master',
    source_type: 'paste',
    source_filename: null,
    original_text: '摘要\n关键词\n引言\n研究方法\n分析与讨论\n结论\n参考文献\n[1] 引用条目 1',
    section_snapshot: [
      { name: '摘要', present: true },
      { name: '结论', present: true },
    ],
    reference_count: 1,
    character_count: 38,
    normative_issues: [],
    score_items: [
      { key: 'section_completeness', label: '章节完整性', points: 30, score: 30, findings: [] },
      { key: 'conclusion_section', label: '结论章节', points: 20, score: 20, findings: [] },
    ],
    total_score: 90,
    result_label: '基础检查通过',
    missing_sections: [],
    rubric_snapshot: {
      template: { template_id: 'academic_master', name: '学术型硕士' },
      shared_score_items: [],
      passing_rule: { minimum_objective_score: 80, no_required_section_missing: true, pass_label: '基础检查通过', revise_label: '需修改' },
    },
    created_at: '2026-03-01T09:00:00.000Z',
    ...overrides,
  };
}

describe('FEAT-AI-REVIEW-HISTORY protected history API contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ai-review-history-api', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-AI-REVIEW-HISTORY:INTEGRATION:AUTHZ:001 denies anonymous history access before returning records', async () => {
    await insertAiReviewRun(reviewRunFixture({ id: 'review-history-anonymous-denied' }));

    await request(app)
      .get('/api/normative/ai-review-runs')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.records).toBeUndefined();
      });
  });

  it('FEAT-AI-REVIEW-HISTORY:INTEGRATION:SCENARIO:001 returns only student01 records newest first with history-list fields', async () => {
    const olderRun = await insertAiReviewRun(reviewRunFixture({
      id: 'review-history-student01-older',
      thesis_title: 'student01 较早评阅论文',
      total_score: 40,
      result_label: '需修改',
      created_at: '2026-03-01T09:00:00.000Z',
    }));
    const newestRun = await insertAiReviewRun(reviewRunFixture({
      id: 'review-history-student01-newest',
      thesis_title: 'student01 最新评阅论文',
      total_score: 92,
      result_label: '基础检查通过',
      created_at: '2026-03-02T10:30:00.000Z',
    }));
    await insertAiReviewRun(reviewRunFixture({
      id: 'review-history-supervisor-excluded',
      user_id: 'supervisor01',
      thesis_title: 'supervisor01 不应出现在学生历史中',
      created_at: '2026-03-03T11:00:00.000Z',
    }));
    const cookie = await login('student01');

    const response = await request(app)
      .get('/api/normative/ai-review-runs')
      .set('Cookie', cookie)
      .expect(200);

    expect(response.body.records).toEqual([
      {
        id: newestRun.id,
        user_id: 'student01',
        thesis_title: 'student01 最新评阅论文',
        template_id: 'academic_master',
        total_score: 92,
        result_label: '基础检查通过',
        created_at: '2026-03-02T10:30:00.000Z',
      },
      {
        id: olderRun.id,
        user_id: 'student01',
        thesis_title: 'student01 较早评阅论文',
        template_id: 'academic_master',
        total_score: 40,
        result_label: '需修改',
        created_at: '2026-03-01T09:00:00.000Z',
      },
    ]);
    expect(response.body.records.map((record) => record.id)).not.toContain('review-history-supervisor-excluded');
    expect(response.body.records[0]).not.toHaveProperty('original_text');
    expect(response.body.records[0]).not.toHaveProperty('score_items');
  });

  it('FEAT-AI-REVIEW-HISTORY:INTEGRATION:AUTHZ:002 excludes another allowed authenticated role owned records through current-user scope', async () => {
    await insertAiReviewRun(reviewRunFixture({
      id: 'review-history-student01-private',
      thesis_title: 'student01 私有历史记录',
      created_at: '2026-04-01T09:00:00.000Z',
    }));
    const supervisorCookie = await login('supervisor01');

    const response = await request(app)
      .get('/api/normative/ai-review-runs')
      .set('Cookie', supervisorCookie)
      .expect(200);

    expect(response.body.records).toEqual([]);
  });
});
