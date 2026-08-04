import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { all, createTestDatabaseHarness, get, run } = require('../src/database');
const {
  createCorpusSample,
  deleteCorpusSample,
  listCorpusSamples,
} = require('../src/normative/duplicationCorpusRepository');

const REQ_ID = 'FEAT-DUPLICATION-CORPUS';
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

function validSamplePayload(overrides = {}) {
  return {
    title: '人工智能课程论文样本',
    subject: '计算机科学',
    year: 2024,
    content: '这是一份用于本地原型相似度检测的非空 UTF-8 文本样本。',
    source_type: 'paste',
    source_filename: null,
    ...overrides,
  };
}

async function corpusSampleCount() {
  const row = await get('SELECT COUNT(*) AS count FROM duplication_corpus_samples');
  return row.count;
}

describe('FEAT-DUPLICATION-CORPUS backend corpus API and SQLite contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'duplication-corpus', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-DUPLICATION-CORPUS:API:AUTHZ:001 enforces anonymous, denied-role, and SCHOOL_ADMIN access at corpus endpoints', async () => {
    await request(app)
      .get('/api/normative/duplication-corpus')
      .expect(401);

    for (const username of ['student01', 'supervisor01', 'college_admin01']) {
      const cookie = await login(username);
      await request(app)
        .post('/api/normative/duplication-corpus')
        .set('Cookie', cookie)
        .send(validSamplePayload())
        .expect(403);
    }

    const beforeCount = await corpusSampleCount();
    const schoolAdminCookie = await login('school_admin01');
    await request(app)
      .post('/api/normative/duplication-corpus')
      .set('Cookie', schoolAdminCookie)
      .send(validSamplePayload({ title: '授权导入样本' }))
      .expect(201)
      .expect(({ body }) => {
        expect(body).toMatchObject({
          title: '授权导入样本',
          subject: '计算机科学',
          year: 2024,
          content: expect.stringContaining('UTF-8 文本样本'),
          source_type: 'paste',
          source_filename: null,
          created_by: 'school_admin01',
          created_at: expect.any(String),
        });
        expect(body.id).toEqual(expect.any(String));
      });
    await expect(corpusSampleCount()).resolves.toBe(beforeCount + 1);
  });

  it('FEAT-DUPLICATION-CORPUS:SCENARIO:001 saves a submitted non-empty UTF-8 sample and returns it for later similarity use', async () => {
    const schoolAdminCookie = await login('school_admin01');
    const payload = validSamplePayload({
      title: '后续相似度检测样本',
      subject: '文学',
      year: 2023,
      content: '这份非空文本将作为后续相似度检测读取的本地比对样本。',
    });

    const response = await request(app)
      .post('/api/normative/duplication-corpus')
      .set('Cookie', schoolAdminCookie)
      .send(payload)
      .expect(201);

    const created = response.body;
    expect(created).toMatchObject({
      title: payload.title,
      subject: payload.subject,
      year: payload.year,
      content: payload.content,
      source_type: 'paste',
      source_filename: null,
      created_by: 'school_admin01',
    });

    const persisted = await get(
      `SELECT title, subject, year, content, source_type AS sourceType, source_filename AS sourceFilename, created_by AS createdBy
         FROM duplication_corpus_samples
        WHERE id = ?`,
      [created.id],
    );
    expect(persisted).toMatchObject({
      title: payload.title,
      subject: payload.subject,
      year: payload.year,
      content: payload.content,
      sourceType: 'paste',
      sourceFilename: null,
      createdBy: 'school_admin01',
    });

    await request(app)
      .get('/api/normative/duplication-corpus')
      .set('Cookie', schoolAdminCookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.samples).toEqual(expect.arrayContaining([
          expect.objectContaining({ id: created.id, title: payload.title, content: payload.content }),
        ]));
      });
  });

  it('FEAT-DUPLICATION-CORPUS:FUNC:VALIDATION:001 rejects blank fields, invalid years, unsupported source metadata, and oversized text without persistence', async () => {
    const schoolAdminCookie = await login('school_admin01');
    const invalidPayloads = [
      validSamplePayload({ title: '   ' }),
      validSamplePayload({ subject: '' }),
      validSamplePayload({ content: '   ' }),
      validSamplePayload({ year: '二零二四' }),
      validSamplePayload({ year: 1799 }),
      validSamplePayload({ source_type: 'file', source_filename: 'sample.pdf' }),
      validSamplePayload({ source_type: 'clipboard' }),
    ];

    for (const payload of invalidPayloads) {
      const beforeCount = await corpusSampleCount();
      await request(app)
        .post('/api/normative/duplication-corpus')
        .set('Cookie', schoolAdminCookie)
        .send(payload)
        .expect(400);
      await expect(corpusSampleCount()).resolves.toBe(beforeCount);
    }

    const beforeOversized = await corpusSampleCount();
    await request(app)
      .post('/api/normative/duplication-corpus')
      .set('Cookie', schoolAdminCookie)
      .send(validSamplePayload({ content: 'a'.repeat(5 * 1024 * 1024 + 1) }))
      .expect(413)
      .expect(({ body }) => {
        expect(body.message).toMatch(/5 MB|超过|过大/);
      });
    await expect(corpusSampleCount()).resolves.toBe(beforeOversized);
  });

  it('FEAT-DUPLICATION-CORPUS:DB:REPOSITORY:001 inserts, orders, maps nullable filenames, and deletes only the requested sample', async () => {
    await run('DELETE FROM duplication_corpus_samples');

    const older = await createCorpusSample({
      title: '较早样本',
      subject: '历史',
      year: 2021,
      content: '较早的本地比对样本文本',
      source_type: 'paste',
      source_filename: null,
      created_by: 'school_admin01',
      created_at: '2024-01-01T00:00:00.000Z',
    });
    const newer = await createCorpusSample({
      title: '较新文件样本',
      subject: '数学',
      year: 2024,
      content: '较新的 Markdown 文件样本文本',
      source_type: 'file',
      source_filename: 'sample.md',
      created_by: 'school_admin01',
      created_at: '2024-02-01T00:00:00.000Z',
    });

    await expect(listCorpusSamples()).resolves.toMatchObject([
      { id: newer.id, source_filename: 'sample.md' },
      { id: older.id, source_filename: null },
    ]);

    await expect(deleteCorpusSample(older.id)).resolves.toBe(true);
    await expect(deleteCorpusSample('missing-sample-id')).resolves.toBe(false);

    const remainingIds = await all('SELECT id FROM duplication_corpus_samples ORDER BY id');
    expect(remainingIds.map((row) => row.id)).toEqual([newer.id]);
  });

  it('FEAT-DUPLICATION-CORPUS:API:DELETE:001 removes a listed sample only after SCHOOL_ADMIN delete succeeds', async () => {
    const schoolAdminCookie = await login('school_admin01');
    const createResponse = await request(app)
      .post('/api/normative/duplication-corpus')
      .set('Cookie', schoolAdminCookie)
      .send(validSamplePayload({ title: '待删除样本' }))
      .expect(201);

    await request(app)
      .delete(`/api/normative/duplication-corpus/${createResponse.body.id}`)
      .set('Cookie', schoolAdminCookie)
      .expect(204);

    await request(app)
      .get('/api/normative/duplication-corpus')
      .set('Cookie', schoolAdminCookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.samples).not.toEqual(expect.arrayContaining([
          expect.objectContaining({ id: createResponse.body.id }),
        ]));
      });

    await request(app)
      .delete('/api/normative/duplication-corpus/missing-sample-id')
      .set('Cookie', schoolAdminCookie)
      .expect(404);
  });
});
