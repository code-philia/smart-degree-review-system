import request from 'supertest';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, run } = require('../src/database');
const { createWholePolishResult } = require('../src/normative/wholePolishRepository');
const { createLocalPolishResult } = require('../src/normative/localPolishRepository');
const {
  ALLOWED_POLISH_HISTORY_ROLES,
  buildPolishResultText,
  ensureCanAccessPolishHistory,
  getPolishHistoryRecordForUser,
  listPolishHistoryForUser,
} = require('../src/normative/polishHistoryService');

const REQ_ID = 'FEAT-POLISH-HISTORY';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

const usersByRole = {
  STUDENT: 'student01',
  SUPERVISOR: 'supervisor01',
  SCHOOL_ADMIN: 'school_admin01',
  COLLEGE_ADMIN: 'college_admin01',
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

function wholeRecord(overrides = {}) {
  return {
    id: overrides.id || `whole-${Date.now()}`,
    user_id: overrides.user_id || 'student01',
    source_type: overrides.source_type || 'file',
    source_filename: overrides.source_filename || 'student01-全文润色.txt',
    original_text: overrides.original_text || '全文原文包含重复重复表达！！',
    polished_text: overrides.polished_text || '全文原文包含重复表达！',
    level: overrides.level || 'standard',
    changes: overrides.changes || [
      { original_text: '重复重复', new_text: '重复', position: 6, rule: '重复词修正' },
      { original_text: '！！', new_text: '！', position: 14, rule: '标点修正' },
    ],
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  };
}

function localRecord(overrides = {}) {
  return {
    id: overrides.id || `local-${Date.now()}`,
    user_id: overrides.user_id || 'student01',
    original_text: overrides.original_text || '局部原文存在重复重复表达！！',
    polished_text: overrides.polished_text || '局部原文存在重复表达！',
    level: overrides.level || 'enhanced',
    rule_version: overrides.rule_version || 'local-polish-v1',
    changes: overrides.changes || [
      { original_text: '重复重复', new_text: '重复', position: 6, rule: '重复词修正' },
    ],
    diff_segments: overrides.diff_segments || [
      { type: 'unchanged', text: '局部原文存在' },
      { type: 'replacement', original_text: '重复重复', text: '重复' },
    ],
    source_result_id: overrides.source_result_id || null,
    retry_of: overrides.retry_of || null,
    created_at: overrides.created_at || '2026-08-04T11:00:00.000Z',
  };
}

async function seedWhole(overrides = {}) {
  return createWholePolishResult(wholeRecord(overrides));
}

async function seedLocal(overrides = {}) {
  return createLocalPolishResult(localRecord(overrides));
}

describe('FEAT-POLISH-HISTORY owned history API, service, and persistence contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'feat-polish-history', seedDefault: true });
    await harness.setup();
  });

  beforeEach(async () => {
    await run('DELETE FROM local_polish_results');
    await run('DELETE FROM whole_polish_results');
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-POLISH-HISTORY:API:AUTHZ:001 denies anonymous history, detail, and TXT download before returning polish data', async () => {
    const ownedRecord = await seedWhole({ id: 'student01-anonymous-history-boundary' });

    await request(app).get('/api/normative/polish-history').expect(401);
    await request(app).get(`/api/normative/polish-history/whole/${ownedRecord.id}`).expect(401);
    await request(app).get(`/api/normative/polish-history/whole/${ownedRecord.id}/download`).expect(401);
  });

  it('FEAT-POLISH-HISTORY:API:ROLES:001 allows every declared role at the owned backend boundary', async () => {
    expect(ALLOWED_POLISH_HISTORY_ROLES).toEqual(['STUDENT', 'SUPERVISOR', 'SCHOOL_ADMIN', 'COLLEGE_ADMIN']);

    for (const [role, username] of Object.entries(usersByRole)) {
      await seedWhole({
        id: `${username}-history-role-record`,
        user_id: username,
        source_filename: `${username}-润色记录.txt`,
        original_text: `${role} 原文重复重复！！`,
        polished_text: `${role} 原文重复！`,
      });
      const cookie = await login(username);

      await request(app)
        .get('/api/normative/polish-history')
        .set('Cookie', cookie)
        .expect(200)
        .expect(({ body }) => {
          expect(body.records).toEqual(expect.arrayContaining([
            expect.objectContaining({
              id: `${username}-history-role-record`,
              user_id: username,
              polish_type: 'whole',
              source_filename: `${username}-润色记录.txt`,
            }),
          ]));
        });
    }
  });

  it('FEAT-POLISH-HISTORY:SCENARIO:001 lists only student01 whole and local records in generation-time descending order', async () => {
    await seedWhole({
      id: 'student01-whole-history-old',
      source_filename: 'student01-全文旧稿.txt',
      level: 'basic',
      created_at: '2026-08-04T09:00:00.000Z',
    });
    await seedLocal({
      id: 'student01-local-history-new',
      level: 'enhanced',
      created_at: '2026-08-04T11:00:00.000Z',
    });
    await seedWhole({
      id: 'supervisor-polish-hidden',
      user_id: 'supervisor01',
      source_filename: 'supervisor-不可见润色.txt',
      created_at: '2026-08-04T12:00:00.000Z',
    });
    const cookie = await login('student01');

    await request(app)
      .get('/api/normative/polish-history')
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.records.map((record) => record.id)).toEqual(['student01-local-history-new', 'student01-whole-history-old']);
        expect(body.records.find((record) => record.id === 'supervisor-polish-hidden')).toBeUndefined();
        expect(body.records[0]).toMatchObject({
          user_id: 'student01',
          polish_type: 'local',
          document_name: '局部润色',
          level: 'enhanced',
          change_count: 1,
          created_at: '2026-08-04T11:00:00.000Z',
        });
        expect(body.records[1]).toMatchObject({
          user_id: 'student01',
          polish_type: 'whole',
          document_name: 'student01-全文旧稿.txt',
          level: 'basic',
          change_count: 2,
          created_at: '2026-08-04T09:00:00.000Z',
        });
      });
  });

  it('FEAT-POLISH-HISTORY:API:DETAIL-DOWNLOAD:001 returns owner-scoped detail, hides another user result, validates type, and downloads persisted polished text', async () => {
    const ownRecord = await seedLocal({
      id: 'student01-download-local-history',
      polished_text: '这是 student01 可下载的局部润色结果。',
      created_at: '2026-08-04T12:00:00.000Z',
    });
    const otherRecord = await seedWhole({ id: 'supervisor-download-polish-hidden', user_id: 'supervisor01' });
    const cookie = await login('student01');

    await request(app)
      .get(`/api/normative/polish-history/whole/${otherRecord.id}`)
      .set('Cookie', cookie)
      .expect(404);

    await request(app)
      .get(`/api/normative/polish-history/invalid/${ownRecord.id}`)
      .set('Cookie', cookie)
      .expect(400);

    await request(app)
      .get(`/api/normative/polish-history/local/${ownRecord.id}`)
      .set('Cookie', cookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body).toMatchObject({
          id: ownRecord.id,
          user_id: 'student01',
          polish_type: 'local',
          polished_text: '这是 student01 可下载的局部润色结果。',
        });
        expect(body.diff_segments).toEqual(ownRecord.diff_segments);
      });

    await request(app)
      .get(`/api/normative/polish-history/local/${ownRecord.id}/download`)
      .set('Cookie', cookie)
      .expect(200)
      .expect('content-type', /text\/plain; charset=utf-8/)
      .expect('content-disposition', new RegExp(`attachment; filename="polish-result-local-${ownRecord.id}\\.txt"`))
      .expect((response) => {
        expect(response.text).toBe('这是 student01 可下载的局部润色结果。');
      });
  });

  it('FEAT-POLISH-HISTORY:FUNC:SERVICE:001 maps missing users and unsupported roles to explicit authorization errors', async () => {
    expect(() => ensureCanAccessPolishHistory(null)).toThrow(expect.objectContaining({ status: 401 }));
    expect(() => ensureCanAccessPolishHistory({ id: 'guest01', role: 'GUEST' })).toThrow(expect.objectContaining({ status: 403 }));
    await expect(listPolishHistoryForUser({ id: 'guest01', role: 'GUEST' })).rejects.toMatchObject({ status: 403 });
    await expect(getPolishHistoryRecordForUser({ id: 'student01', role: 'STUDENT' }, 'whole', '')).rejects.toMatchObject({ status: 400 });
    expect(buildPolishResultText({ polished_text: '持久化润色文本' })).toBe('持久化润色文本');
  });
});
