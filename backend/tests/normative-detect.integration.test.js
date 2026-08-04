import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get } = require('../src/database');

const REQ_ID = 'FEAT-NORMATIVE-DETECT';
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

async function detectionTaskCount() {
  const row = await get('SELECT COUNT(*) AS count FROM normative_detection_tasks');
  return row.count;
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

function scenarioText() {
  const longSentence = `这是一个超过一百二十字符的句子${'问题'.repeat(70)}。`;
  return [
    '摘要',
    '关键词：规范检测；规则快照',
    '引言',
    `这里包含未配对（括号。。${longSentence}`,
    '结论',
    '参考文献',
    '[1] 示例文献',
  ].join('\n');
}

describe('FEAT-NORMATIVE-DETECT protected task creation contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-normative-detect', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-NORMATIVE-DETECT:API:001 denies anonymous detection task creation before persistence', async () => {
    const beforeCount = await detectionTaskCount();

    await request(app)
      .post('/api/normative/detection-tasks')
      .send({ text: scenarioText(), source_type: 'paste' })
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.id).toBeUndefined();
      });

    await expect(detectionTaskCount()).resolves.toBe(beforeCount);
  });

  it('FEAT-NORMATIVE-DETECT:API:002 allows every declared authenticated role to create a completed persisted task', async () => {
    const usernames = ['student01', 'supervisor01', 'college_admin01', 'school_admin01'];

    for (const username of usernames) {
      const cookie = await login(username);

      await request(app)
        .post('/api/normative/detection-tasks')
        .set('Cookie', cookie)
        .send({ text: scenarioText(), source_type: 'paste' })
        .expect(201)
        .expect(({ body }) => {
          expect(body.status).toBe('completed');
          expect(body.user_id).toBe(username);
          expect(body.original_text).toContain('摘要');
          expect(Array.isArray(body.rule_snapshot)).toBe(true);
          expect(body.rule_snapshot.length).toBeGreaterThan(0);
          expect(Array.isArray(body.issues)).toBe(true);
          expect(body.created_at).toEqual(expect.any(String));
        });
    }
  });

  it('FEAT-NORMATIVE-DETECT:SCENARIO:001 saves completed pasted-text task with rule snapshot, issue positions, severity counts, and created time', async () => {
    const cookie = await login('student01');
    const text = scenarioText();

    const response = await request(app)
      .post('/api/normative/detection-tasks')
      .set('Cookie', cookie)
      .send({ text, source_type: 'paste' })
      .expect(201);

    const task = response.body;
    expect(task).toMatchObject({
      user_id: 'student01',
      status: 'completed',
      source_type: 'paste',
      source_filename: null,
      original_text: text,
      created_at: expect.any(String),
    });
    expect(task.status).not.toBe('pending');
    expect(task.status).not.toBe('running');
    expect(Array.isArray(task.rule_snapshot)).toBe(true);
    expect(task.rule_snapshot.length).toBeGreaterThan(0);
    expect(Array.isArray(task.issues)).toBe(true);
    expect(task.issues.length).toBeGreaterThan(0);
    task.issues.forEach(expectIssueShape);

    const countedIssues = task.issues.reduce((counts, issue) => {
      counts[issue.severity] = (counts[issue.severity] || 0) + 1;
      return counts;
    }, {});
    expect(task.severity_counts).toEqual(countedIssues);

    const persisted = await get(
      `SELECT status, source_type AS sourceType, original_text AS originalText,
              rule_snapshot_json AS ruleSnapshotJson, issues_json AS issuesJson,
              severity_counts_json AS severityCountsJson, created_at AS createdAt
         FROM normative_detection_tasks
        WHERE id = ?`,
      [task.id],
    );
    expect(persisted).toMatchObject({
      status: 'completed',
      sourceType: 'paste',
      originalText: text,
      createdAt: task.created_at,
    });
    expect(JSON.parse(persisted.ruleSnapshotJson)).toEqual(task.rule_snapshot);
    expect(JSON.parse(persisted.issuesJson)).toEqual(task.issues);
    expect(JSON.parse(persisted.severityCountsJson)).toEqual(task.severity_counts);
  });

  it('FEAT-NORMATIVE-DETECT:SCENARIO:002 rejects oversized submitted content with understandable error and creates no task', async () => {
    const cookie = await login('student01');
    const beforeCount = await detectionTaskCount();

    await request(app)
      .post('/api/normative/detection-tasks')
      .set('Cookie', cookie)
      .send({ text: 'a'.repeat(5 * 1024 * 1024 + 1), source_type: 'file', source_filename: 'oversized.txt' })
      .expect(413)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 413 });
        expect(body.message).toMatch(/5 MB|超过|过大/);
        expect(body.id).toBeUndefined();
      });

    await expect(detectionTaskCount()).resolves.toBe(beforeCount);
  });
});
