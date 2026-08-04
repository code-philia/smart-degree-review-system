import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const {
  createWholePolishResult: createWholePolishResultInRepository,
  getWholePolishResultForUser: getWholePolishResultForUserInRepository,
} = require('../src/normative/wholePolishRepository');
const {
  ALLOWED_WHOLE_POLISH_ROLES,
  buildDownloadText,
  createWholePolishResult,
  getWholePolishResultForUser,
} = require('../src/normative/wholePolishService');

const REQ_ID = 'FEAT-POLISH-WHOLE';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

const usersByRole = {
  STUDENT: 'student01',
  SUPERVISOR: 'supervisor01',
  SCHOOL_ADMIN: 'school_admin01',
  COLLEGE_ADMIN: 'college_admin01',
};

const student = {
  id: 'student01',
  username: 'student01',
  role: 'STUDENT',
  collegeId: 'college01',
  scope: 'COLLEGE',
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

async function seedPhraseMapping(originalPhrase = '低效表达', replacementPhrase = '高效表达') {
  await run(
    `INSERT INTO normative_rule_overrides (
       id, scope_level, college_id, rule_id, title, category, severity, enabled, match_params_json, prompt, updated_by, updated_at
     ) VALUES (?, 'school', NULL, 'WHOLE-POLISH-PHRASE-MAP', '全文润色短语映射', '全文润色', 'medium', 1, ?, '应用管理员维护的原短语到替换短语映射', 'school_admin01', CURRENT_TIMESTAMP)
     ON CONFLICT(scope_level, college_id, rule_id) DO UPDATE SET
       title = excluded.title,
       category = excluded.category,
       severity = excluded.severity,
       enabled = excluded.enabled,
       match_params_json = excluded.match_params_json,
       prompt = excluded.prompt,
       updated_by = excluded.updated_by,
       updated_at = CURRENT_TIMESTAMP`,
    [
      'school:whole-polish-phrase-map',
      JSON.stringify({ replacements: [{ original: originalPhrase, replacement: replacementPhrase }] }),
    ],
  );
}

function wholePolishPayload(overrides = {}) {
  return {
    text: '这里存在重复重复词！！  并包含低效表达。',
    level: 'standard',
    source_type: 'paste',
    source_filename: null,
    ...overrides,
  };
}

describe('FEAT-POLISH-WHOLE backend whole-text polishing contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-polish-whole', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM whole_polish_results');
    await run("DELETE FROM normative_rule_overrides WHERE rule_id = 'WHOLE-POLISH-PHRASE-MAP'");
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-POLISH-WHOLE:API:AUTHZ:001 denies anonymous access and allows every declared role to create persisted polishing results', async () => {
    expect(ALLOWED_WHOLE_POLISH_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);
    await seedPhraseMapping();

    await request(app)
      .post('/api/normative/whole-polish-results')
      .send(wholePolishPayload())
      .expect(401);

    for (const [role, username] of Object.entries(usersByRole)) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/whole-polish-results')
        .set('Cookie', cookie)
        .send(wholePolishPayload({ text: `${role} 重复重复！！ 低效表达。` }))
        .expect(201)
        .expect(({ body }) => {
          expect(body).toMatchObject({
            user_id: username,
            source_type: 'paste',
            source_filename: null,
            level: 'standard',
            original_text: `${role} 重复重复！！ 低效表达。`,
          });
          expect(body.polished_text).toContain('高效表达');
          expect(body.polished_text).not.toContain('重复重复');
          expect(body.polished_text).not.toContain('！！');
          expect(body.changes.length).toBeGreaterThanOrEqual(3);
          for (const change of body.changes) {
            expect(change).toEqual(expect.objectContaining({
              original_text: expect.any(String),
              new_text: expect.any(String),
              position: expect.any(Number),
              rule: expect.any(String),
            }));
          }
        });
    }
  });

  it('FEAT-POLISH-WHOLE:SCENARIO:001 standard optimization produces deterministic text and traceable changes for duplicate punctuation, duplicate words, and a configured phrase', async () => {
    await seedPhraseMapping('低效表达', '高效表达');

    const result = await createWholePolishResult(student, wholePolishPayload({
      text: '第一段有重复重复词！！  同时包含低效表达。',
      source_type: 'paste',
    }));

    expect(result).toMatchObject({
      user_id: 'student01',
      source_type: 'paste',
      source_filename: null,
      level: 'standard',
      original_text: '第一段有重复重复词！！  同时包含低效表达。',
      polished_text: '第一段有重复词！ 同时包含高效表达。',
    });
    expect(result.changes).toEqual(expect.arrayContaining([
      expect.objectContaining({ original_text: '！！', new_text: '！', position: expect.any(Number), rule: expect.stringMatching(/标点|punctuation/i) }),
      expect.objectContaining({ original_text: '重复重复', new_text: '重复', position: expect.any(Number), rule: expect.stringMatching(/重复词|word/i) }),
      expect.objectContaining({ original_text: '低效表达', new_text: '高效表达', position: expect.any(Number), rule: expect.stringMatching(/短语|phrase|mapping/i) }),
    ]));

    const persisted = await get('SELECT original_text AS originalText, polished_text AS polishedText, level, changes_json AS changesJson FROM whole_polish_results WHERE id = ?', [result.id]);
    expect(persisted).toMatchObject({
      originalText: result.original_text,
      polishedText: result.polished_text,
      level: 'standard',
    });
    expect(JSON.parse(persisted.changesJson)).toEqual(result.changes);
  });

  it('FEAT-POLISH-WHOLE:FUNC:LEVELS:001 applies basic, standard, and enhanced rules in order with split reasons for legal long-sentence separators', async () => {
    await seedPhraseMapping('低效表达', '高效表达');
    const longSegment = `${'长句内容'.repeat(18)}，后半句继续说明增强优化需要在首个合法分隔位置拆分并记录原因。`;

    const basic = await createWholePolishResult(student, wholePolishPayload({ text: '行尾空格   \n重复重复？？  低效表达。', level: 'basic' }));
    const standard = await createWholePolishResult(student, wholePolishPayload({ text: '行尾空格   \n重复重复？？  低效表达。', level: 'standard' }));
    const enhanced = await createWholePolishResult(student, wholePolishPayload({ text: longSegment, level: 'enhanced' }));

    expect(basic.polished_text).not.toContain('？？');
    expect(basic.polished_text).not.toContain('重复重复');
    expect(basic.polished_text).toContain('低效表达');
    expect(standard.polished_text).toContain('高效表达');
    expect(enhanced.polished_text).toContain('，\n');
    expect(enhanced.changes).toEqual(expect.arrayContaining([
      expect.objectContaining({
        original_text: '，',
        new_text: '，\n',
        position: expect.any(Number),
        rule: expect.stringMatching(/拆分|split/i),
        reason: expect.stringMatching(/120|分隔|separator|long/i),
      }),
    ]));
  });

  it('FEAT-POLISH-WHOLE:API:READ-DOWNLOAD:001 scopes result reads by owner and downloads only polished UTF-8 text', async () => {
    await seedPhraseMapping();
    const studentCookie = await login('student01');
    const supervisorCookie = await login('supervisor01');
    const createResponse = await request(app)
      .post('/api/normative/whole-polish-results')
      .set('Cookie', studentCookie)
      .send(wholePolishPayload({ text: '下载下载测试！！ 低效表达。', source_type: 'file', source_filename: 'paper.md' }))
      .expect(201);

    const result = createResponse.body;
    await request(app)
      .get(`/api/normative/whole-polish-results/${result.id}`)
      .set('Cookie', supervisorCookie)
      .expect(404);
    await request(app)
      .get(`/api/normative/whole-polish-results/${result.id}/download`)
      .set('Cookie', supervisorCookie)
      .expect(404);

    await request(app)
      .get(`/api/normative/whole-polish-results/${result.id}`)
      .set('Cookie', studentCookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body).toMatchObject({ id: result.id, user_id: 'student01', source_filename: 'paper.md' });
        expect(body.changes).toEqual(result.changes);
      });

    await request(app)
      .get(`/api/normative/whole-polish-results/${result.id}/download`)
      .set('Cookie', studentCookie)
      .expect(200)
      .expect('content-type', /text\/plain; charset=utf-8/)
      .expect('content-disposition', new RegExp(`attachment; filename="whole-polish-${result.id}\\.txt"`))
      .expect(({ text }) => {
        expect(text).toBe(result.polished_text);
        expect(text).not.toContain(result.original_text);
      });
  });

  it('FEAT-POLISH-WHOLE:DB:REPOSITORY:001 stores changes as JSON, filters by user id, handles malformed change JSON, and enforces schema constraints', async () => {
    const stored = await createWholePolishResultInRepository({
      id: 'whole-polish-repository-record',
      user_id: 'student01',
      source_type: 'file',
      source_filename: 'thesis.txt',
      original_text: '原文',
      polished_text: '新文',
      level: 'enhanced',
      changes: [{ original_text: '原文', new_text: '新文', position: 0, rule: '测试规则' }],
      created_at: '2026-08-04T10:00:00.000Z',
    });

    expect(stored).toMatchObject({ id: 'whole-polish-repository-record', changes: [{ rule: '测试规则' }] });
    await expect(getWholePolishResultForUserInRepository('student01', stored.id)).resolves.toMatchObject({ id: stored.id });
    await expect(getWholePolishResultForUserInRepository('supervisor01', stored.id)).resolves.toBeNull();
    await expect(getWholePolishResultForUser(student, stored.id)).resolves.toMatchObject({ id: stored.id });
    expect(buildDownloadText(stored)).toBe('新文');

    await run("UPDATE whole_polish_results SET changes_json = 'not-json' WHERE id = ?", [stored.id]);
    await expect(getWholePolishResultForUserInRepository('student01', stored.id)).resolves.toMatchObject({ changes: [] });

    await expect(run(
      `INSERT INTO whole_polish_results (id, user_id, source_type, source_filename, original_text, polished_text, level, changes_json)
       VALUES ('invalid-source', 'student01', 'clipboard', NULL, '原文', '新文', 'basic', '[]')`,
    )).rejects.toThrow();
    await expect(run(
      `INSERT INTO whole_polish_results (id, user_id, source_type, source_filename, original_text, polished_text, level, changes_json)
       VALUES ('invalid-level', 'student01', 'paste', NULL, '原文', '新文', 'expert', '[]')`,
    )).rejects.toThrow();
  });
});
