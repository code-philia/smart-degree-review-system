import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get } = require('../src/database');

const REQ_ID = 'FEAT-AI-REVIEW-RUN';
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

function buildMissingConclusionText(referenceCount = 50) {
  return [
    '摘要',
    '关键词',
    '引言',
    '研究方法',
    '分析与讨论',
    '参考文献',
    buildReferenceLines(referenceCount),
  ].join('\n');
}

describe('FEAT-AI-REVIEW-RUN protected AI review run API contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-ai-review-run-api', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('denies anonymous review-run creation before returning any persisted result', async () => {
    await request(app)
      .post('/api/normative/ai-review-runs')
      .send({
        thesis_title: '高校数字治理平台评阅研究',
        template_id: 'academic_master',
        text: buildMissingConclusionText(),
        source_type: 'paste',
      })
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.id).toBeUndefined();
        expect(body.result_label).toBeUndefined();
      });
  });

  it('creates a persisted student review run whose conclusion item scores 0 and result label is 需修改', async () => {
    const cookie = await login('student01');
    const text = buildMissingConclusionText();

    const response = await request(app)
      .post('/api/normative/ai-review-runs')
      .set('Cookie', cookie)
      .send({
        thesis_title: '高校数字治理平台评阅研究',
        template_id: 'academic_master',
        text,
        source_type: 'paste',
      })
      .expect(201);

    const body = response.body;
    expect(body).toMatchObject({
      user_id: 'student01',
      thesis_title: '高校数字治理平台评阅研究',
      template_id: 'academic_master',
      source_type: 'paste',
      source_filename: null,
      original_text: text,
      reference_count: 50,
      result_label: '需修改',
      missing_sections: ['结论'],
      created_at: expect.any(String),
    });
    expect(body.score_items).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ key: 'conclusion_section', score: 0, findings: ['缺少结论章节'] }),
      ]),
    );
    expect(body.rubric_snapshot.template.template_id).toBe('academic_master');

    const persisted = await get(
      `SELECT user_id, thesis_title, template_id, source_type, source_filename,
              original_text, reference_count, character_count, result_label,
              missing_sections_json AS missingSectionsJson,
              score_items_json AS scoreItemsJson,
              rubric_snapshot_json AS rubricSnapshotJson
         FROM ai_review_runs
        WHERE id = ?`,
      [body.id],
    );
    expect(persisted).toMatchObject({
      user_id: 'student01',
      thesis_title: '高校数字治理平台评阅研究',
      template_id: 'academic_master',
      source_type: 'paste',
      source_filename: null,
      original_text: text,
      reference_count: 50,
      result_label: '需修改',
    });
    expect(JSON.parse(persisted.missingSectionsJson)).toEqual(['结论']);
    expect(JSON.parse(persisted.scoreItemsJson)).toEqual(body.score_items);
    expect(JSON.parse(persisted.rubricSnapshotJson).template.template_id).toBe('academic_master');
  });

  it('rejects oversized review text with 413 rather than persisting a fake success', async () => {
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/ai-review-runs')
      .set('Cookie', cookie)
      .send({
        thesis_title: '高校数字治理平台评阅研究',
        template_id: 'academic_master',
        text: 'a'.repeat(5 * 1024 * 1024 + 1),
        source_type: 'paste',
      })
      .expect(413)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 413 });
        expect(body.message).toMatch(/5 MB|超过|过大/);
        expect(body.id).toBeUndefined();
      });
  });
});
