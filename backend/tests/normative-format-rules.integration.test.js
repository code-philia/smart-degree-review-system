import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness } = require('../src/database');

const REQ_ID = 'FEAT-NORMATIVE-FORMAT-RULES';
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

function expectIssueShape(issue) {
  expect(issue).toEqual(expect.objectContaining({
    rule_id: expect.any(String),
    category: expect.any(String),
    severity: expect.any(String),
    line: expect.any(Number),
    column: expect.any(Number),
    excerpt: expect.any(String),
    message: expect.any(String),
    suggestion: expect.any(String),
  }));
  expect(issue.line).toBeGreaterThanOrEqual(1);
  expect(issue.column).toBeGreaterThanOrEqual(1);
}

describe('FEAT-NORMATIVE-FORMAT-RULES protected API contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-normative-format-rules', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('denies anonymous listing and analysis requests before returning rule data or analysis results', async () => {
    await request(app)
      .get('/api/normative/rules')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.rules).toBeUndefined();
      });

    await request(app)
      .post('/api/normative/analyze')
      .send({ text: '摘要\n关键词\n引言\n正文。\n结论\n参考文献\n[1] 示例文献' })
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.issues).toBeUndefined();
      });
  });

  it('allows every authenticated role in the role catalog to run default normative analysis', async () => {
    const validText = '摘要\n关键词\n引言\n正文。\n结论\n参考文献\n[1] 示例文献';
    const usernames = ['student01', 'supervisor01', 'college_admin01', 'school_admin01'];

    for (const username of usernames) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/analyze')
        .set('Cookie', cookie)
        .send({ text: validText })
        .expect(200)
        .expect(({ body }) => {
          expect(body).toHaveProperty('issues');
          expect(Array.isArray(body.issues)).toBe(true);
        });
    }
  });

  it('rejects blank text with 400 at the HTTP boundary', async () => {
    const cookie = await login('student01');

    await request(app)
      .post('/api/normative/analyze')
      .set('Cookie', cookie)
      .send({ text: '   \n\t  ' })
      .expect(400)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 400 });
        expect(body.issues).toBeUndefined();
      });
  });

  it('returns separate scenario issues with required fields through the mounted backend app route', async () => {
    const cookie = await login('student01');
    const longSentence = `这是一个超过一百二十字符的句子${'问题'.repeat(70)}。`;
    const scenarioText = [
      '摘要',
      '关键词',
      '引言',
      `学生文本包含未配对（括号。。${longSentence}`,
      '结论',
      '参考文献',
      '[1] 示例文献',
    ].join('\n');

    await request(app)
      .post('/api/normative/analyze')
      .set('Cookie', cookie)
      .send({ text: scenarioText })
      .expect(200)
      .expect(({ body }) => {
        expect(Array.isArray(body.issues)).toBe(true);
        const pairingIssue = body.issues.find((issue) => issue.category === '标点配对' && issue.excerpt.includes('（'));
        const repeatedPunctuationIssue = body.issues.find((issue) => issue.category === '重复标点' && issue.excerpt.includes('。。'));
        const longSentenceIssue = body.issues.find((issue) => issue.category === '文本质量' && issue.message.includes('120'));

        expect(pairingIssue).toBeTruthy();
        expect(repeatedPunctuationIssue).toBeTruthy();
        expect(longSentenceIssue).toBeTruthy();
        [pairingIssue, repeatedPunctuationIssue, longSentenceIssue].forEach(expectIssueShape);
      });
  });
});
