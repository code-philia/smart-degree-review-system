import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const {
  createLocalPolishResult: createLocalPolishResultInRepository,
  getLocalPolishResultForUser: getLocalPolishResultForUserInRepository,
} = require('../src/normative/localPolishRepository');
const {
  ALLOWED_LOCAL_POLISH_ROLES,
  LOCAL_POLISH_RULE_VERSION,
  createLocalPolishResult,
  getLocalPolishResultForUser,
} = require('../src/normative/localPolishService');

const REQ_ID = 'FEAT-POLISH-LOCAL';
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

function localPolishPayload(overrides = {}) {
  return {
    text: '这里存在重复重复词！！  需要局部润色。',
    level: 'standard',
    ...overrides,
  };
}

describe('FEAT-POLISH-LOCAL backend local polishing contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-polish-local', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM local_polish_results');
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-POLISH-LOCAL:API:AUTHZ:001 denies anonymous access and allows every declared role to create local polishing results', async () => {
    expect(ALLOWED_LOCAL_POLISH_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

    await request(app)
      .post('/api/normative/local-polish-results')
      .send(localPolishPayload())
      .expect(401);

    await request(app)
      .get('/api/normative/local-polish-results/missing-result')
      .expect(401);

    for (const [role, username] of Object.entries(usersByRole)) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/local-polish-results')
        .set('Cookie', cookie)
        .send(localPolishPayload({ text: `${role} 重复重复！！  局部润色文本。` }))
        .expect(201)
        .expect(({ body }) => {
          expect(body).toMatchObject({
            user_id: username,
            level: 'standard',
            original_text: `${role} 重复重复！！  局部润色文本。`,
            rule_version: LOCAL_POLISH_RULE_VERSION,
          });
          expect(body.id).toEqual(expect.any(String));
          expect(body.polished_text).toEqual(expect.any(String));
          expect(body.changes.length).toBeGreaterThan(0);
          expect(body.diff_segments.length).toBeGreaterThan(0);
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

  it('FEAT-POLISH-LOCAL:SCENARIO:001 retry with the same original text, standard level, and rule version returns byte-identical content fields', async () => {
    const cookie = await login('student01');
    const firstResponse = await request(app)
      .post('/api/normative/local-polish-results')
      .set('Cookie', cookie)
      .send(localPolishPayload({ text: '第一段存在重复重复表达！！  需要标准优化。' }))
      .expect(201);

    const retryResponse = await request(app)
      .post('/api/normative/local-polish-results')
      .set('Cookie', cookie)
      .send(localPolishPayload({
        text: firstResponse.body.original_text,
        level: firstResponse.body.level,
        retry_of: firstResponse.body.id,
      }))
      .expect(201);

    expect(retryResponse.body).toMatchObject({
      user_id: 'student01',
      original_text: firstResponse.body.original_text,
      level: 'standard',
      rule_version: firstResponse.body.rule_version,
      retry_of: firstResponse.body.id,
    });
    expect(retryResponse.body.polished_text).toBe(firstResponse.body.polished_text);
    expect(JSON.stringify(retryResponse.body.changes)).toBe(JSON.stringify(firstResponse.body.changes));
    expect(JSON.stringify(retryResponse.body.diff_segments)).toBe(JSON.stringify(firstResponse.body.diff_segments));
  });

  it('FEAT-POLISH-LOCAL:API:READ-SCOPE:001 reads only owner-scoped local polishing results', async () => {
    const studentCookie = await login('student01');
    const supervisorCookie = await login('supervisor01');
    const createResponse = await request(app)
      .post('/api/normative/local-polish-results')
      .set('Cookie', studentCookie)
      .send(localPolishPayload({ text: '归属读取测试重复重复！！' }))
      .expect(201);

    await request(app)
      .get(`/api/normative/local-polish-results/${createResponse.body.id}`)
      .set('Cookie', supervisorCookie)
      .expect(404);

    await request(app)
      .get(`/api/normative/local-polish-results/${createResponse.body.id}`)
      .set('Cookie', studentCookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body).toMatchObject({ id: createResponse.body.id, user_id: 'student01' });
        expect(body.changes).toEqual(createResponse.body.changes);
        expect(body.diff_segments).toEqual(createResponse.body.diff_segments);
      });
  });

  it('FEAT-POLISH-LOCAL:FUNC:VALIDATION:001 rejects blank text, unsupported levels, and non-owned lookups', async () => {
    await expect(createLocalPolishResult(student, localPolishPayload({ text: '   ' }))).rejects.toMatchObject({ status: 400 });
    await expect(createLocalPolishResult(student, localPolishPayload({ level: 'expert' }))).rejects.toMatchObject({ status: 400 });
    await expect(getLocalPolishResultForUser(student, 'missing-local-result')).rejects.toMatchObject({ status: 404 });

    const basic = await createLocalPolishResult(student, localPolishPayload({ text: '同一文本重复重复！！', level: 'basic' }));
    const enhanced = await createLocalPolishResult(student, localPolishPayload({ text: '同一文本重复重复！！', level: 'enhanced' }));
    expect(enhanced.polished_text).not.toBe(basic.polished_text);
  });

  it('FEAT-POLISH-LOCAL:DB:REPOSITORY:001 stores JSON arrays, filters by user id, handles malformed JSON arrays, and enforces level constraints', async () => {
    const stored = await createLocalPolishResultInRepository({
      id: 'local-polish-repository-record',
      user_id: 'student01',
      original_text: '原文',
      polished_text: '新文',
      level: 'enhanced',
      rule_version: LOCAL_POLISH_RULE_VERSION,
      changes: [{ original_text: '原文', new_text: '新文', position: 0, rule: '测试规则' }],
      diff_segments: [{ type: 'replacement', original_text: '原文', text: '新文' }],
      source_result_id: null,
      retry_of: null,
      created_at: '2026-08-04T10:00:00.000Z',
    });

    expect(stored).toMatchObject({ id: 'local-polish-repository-record', changes: [{ rule: '测试规则' }] });
    await expect(getLocalPolishResultForUserInRepository('student01', stored.id)).resolves.toMatchObject({ id: stored.id });
    await expect(getLocalPolishResultForUserInRepository('supervisor01', stored.id)).resolves.toBeNull();

    const persisted = await get('SELECT changes_json AS changesJson, diff_segments_json AS diffSegmentsJson FROM local_polish_results WHERE id = ?', [stored.id]);
    expect(JSON.parse(persisted.changesJson)).toEqual(stored.changes);
    expect(JSON.parse(persisted.diffSegmentsJson)).toEqual(stored.diff_segments);

    await run("UPDATE local_polish_results SET changes_json = 'not-json', diff_segments_json = 'not-json' WHERE id = ?", [stored.id]);
    await expect(getLocalPolishResultForUserInRepository('student01', stored.id)).resolves.toMatchObject({
      changes: [],
      diff_segments: [],
    });

    await expect(run(
      `INSERT INTO local_polish_results (id, user_id, original_text, polished_text, level, rule_version, changes_json, diff_segments_json)
       VALUES ('invalid-local-level', 'student01', '原文', '新文', 'expert', ?, '[]', '[]')`,
      [LOCAL_POLISH_RULE_VERSION],
    )).rejects.toThrow();
  });
});
