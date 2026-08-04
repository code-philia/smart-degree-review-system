import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, all, get, run } = require('../src/database');
const { importRuleDraftTemplate } = require('../src/normative/ruleDraftImportService');
const { listRuleDrafts } = require('../src/normative/ruleDraftRepository');

const REQ_ID = 'FEAT-RULE-TEMPLATE-UPLOAD';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
let harness;

const schoolAdmin = {
  id: 'school_admin01',
  username: 'school_admin01',
  role: 'SCHOOL_ADMIN',
  collegeId: null,
  scope: 'SCHOOL',
};

const collegeAdmin = {
  id: 'college_admin01',
  username: 'college_admin01',
  role: 'COLLEGE_ADMIN',
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

function validRuleDrafts() {
  return [
    {
      rule_id: 'UPLOAD-001',
      title: '标题完整性',
      category: '结构规范',
      severity: '严重',
      enabled: true,
      message: '标题必须完整',
      params: { required: true },
    },
    {
      rule_id: 'UPLOAD-002',
      title: '参考文献格式',
      category: '引用规范',
      severity: '一般',
      enabled: false,
      message: '参考文献格式需统一',
    },
  ];
}

async function seedActiveOverride() {
  await run(
    `INSERT INTO normative_rule_overrides (
       id, scope_level, college_id, rule_id, title, category, severity, enabled, match_params_json, prompt, updated_by, updated_at
     ) VALUES (?, 'school', NULL, 'TEXT-LONG-SENTENCE', '长句字符阈值', '文本质量', 'medium', 1, ?, '已生效规则保持不变', 'test-setup', CURRENT_TIMESTAMP)
     ON CONFLICT(scope_level, college_id, rule_id) DO UPDATE SET
       match_params_json = excluded.match_params_json,
       prompt = excluded.prompt`,
    ['school:TEXT-LONG-SENTENCE', JSON.stringify({ max_chars: 120 })],
  );
}

describe('FEAT-RULE-TEMPLATE-UPLOAD backend draft import contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'rule-template-upload', seedDefault: true });
    await harness.setup();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:API:AUTHZ:001 enforces anonymous, denied-role, and allowed-role access at the import endpoint', async () => {
    await request(app)
      .post('/api/normative/rule-drafts/import')
      .set('Content-Type', 'application/json; charset=utf-8')
      .send(JSON.stringify(validRuleDrafts()))
      .expect(401);

    const studentCookie = await login('student01');
    await request(app)
      .post('/api/normative/rule-drafts/import')
      .set('Cookie', studentCookie)
      .set('Content-Type', 'application/json; charset=utf-8')
      .send(JSON.stringify(validRuleDrafts()))
      .expect(403);

    const supervisorCookie = await login('supervisor01');
    await request(app)
      .post('/api/normative/rule-drafts/import')
      .set('Cookie', supervisorCookie)
      .set('Content-Type', 'application/json; charset=utf-8')
      .send(JSON.stringify(validRuleDrafts()))
      .expect(403);

    const schoolCookie = await login('school_admin01');
    await request(app)
      .post('/api/normative/rule-drafts/import')
      .set('Cookie', schoolCookie)
      .set('Content-Type', 'application/json; charset=utf-8')
      .send(JSON.stringify(validRuleDrafts()))
      .expect(201)
      .expect(({ body }) => {
        expect(body.imported_count).toBe(2);
        expect(body.scope).toMatchObject({ level: 'school' });
      });
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:SCENARIO:001 creates two school draft rows and leaves active overrides unchanged', async () => {
    await seedActiveOverride();
    const schoolCookie = await login('school_admin01');

    await request(app)
      .post('/api/normative/rule-drafts/import')
      .set('Cookie', schoolCookie)
      .set('Content-Type', 'application/json; charset=utf-8')
      .send(JSON.stringify(validRuleDrafts()))
      .expect(201)
      .expect(({ body }) => {
        expect(body.imported_count).toBe(2);
        expect(body.draft_batch_id).toEqual(expect.any(String));
        expect(body.drafts).toHaveLength(2);
        expect(body.drafts.map((draft) => draft.rule_id)).toEqual(['UPLOAD-001', 'UPLOAD-002']);
      });

    const drafts = await listRuleDrafts({ level: 'school' });
    const activeOverride = await get(
      `SELECT match_params_json AS matchParamsJson, prompt
         FROM normative_rule_overrides
        WHERE scope_level = 'school' AND rule_id = 'TEXT-LONG-SENTENCE'`,
    );

    expect(drafts).toHaveLength(2);
    expect(drafts.map((draft) => draft.rule_id)).toEqual(['UPLOAD-001', 'UPLOAD-002']);
    expect(JSON.parse(activeOverride.matchParamsJson)).toMatchObject({ max_chars: 120 });
    expect(activeOverride.prompt).toBe('已生效规则保持不变');
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:SCENARIO:002 reports item-indexed validation errors and saves no college drafts', async () => {
    const invalidDrafts = [
      {
        title: '缺少规则编号',
        category: '结构规范',
        severity: '严重',
        enabled: true,
        message: '缺少 rule_id',
      },
      {
        rule_id: 'UPLOAD-BAD-SEVERITY',
        title: '非法严重程度',
        category: '结构规范',
        severity: '紧急',
        enabled: true,
        message: 'severity 不在允许范围',
      },
    ];

    await expect(importRuleDraftTemplate(collegeAdmin, {
      content: Buffer.from(JSON.stringify(invalidDrafts), 'utf8'),
      contentType: 'application/json; charset=utf-8',
      fileName: 'invalid-rules.json',
    })).rejects.toMatchObject({
      status: 400,
      errors: expect.arrayContaining([
        expect.objectContaining({ item_index: 0, field: 'rule_id' }),
        expect.objectContaining({ item_index: 1, field: 'severity' }),
      ]),
    });

    const savedDrafts = await all(
      `SELECT rule_id FROM normative_rule_drafts WHERE scope_level = 'college' AND college_id = 'college01'`,
    );
    expect(savedDrafts).toEqual([]);
  });

  it('FEAT-RULE-TEMPLATE-UPLOAD:API:SIZE:001 rejects uploads larger than 1 MB before draft persistence', async () => {
    const schoolCookie = await login('school_admin01');
    const oversizedBody = `[${' '.repeat(1024 * 1024)}]`;

    await request(app)
      .post('/api/normative/rule-drafts/import')
      .set('Cookie', schoolCookie)
      .set('Content-Type', 'application/json; charset=utf-8')
      .send(oversizedBody)
      .expect(413);
  });
});
