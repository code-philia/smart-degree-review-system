import request from 'supertest';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const app = require('../src/app');
const { createTestDatabaseHarness, get, run } = require('../src/database');
const {
  listEffectiveRuleConfigurations,
  publishRuleConfiguration,
  resetCollegeRuleConfiguration,
  resolveRulesForAnalysis,
} = require('../src/normative/ruleConfigService');

const REQ_ID = 'FLOW-RULE-PUBLISH';
void REQ_ID;

const demoPassword = 'ArcDemo123!';
const schoolAdmin = {
  id: 'school_admin01',
  username: 'school_admin01',
  role: 'SCHOOL_ADMIN',
  collegeId: null,
  scope: 'SCHOOL',
};
const college01Admin = {
  id: 'college_admin01',
  username: 'college_admin01',
  role: 'COLLEGE_ADMIN',
  collegeId: 'college01',
  scope: 'COLLEGE',
};
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

async function seedCollege02Student() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college02', 'supervisor01', 'COLLEGE'
       FROM auth_users
      WHERE username = 'student01'
     ON CONFLICT(id) DO UPDATE SET college_id = excluded.college_id`,
  );
}

function textLongSentenceRule(threshold, prompt = '长句阈值提示') {
  return {
    rule_id: 'TEXT-LONG-SENTENCE',
    title: '长句字符阈值',
    category: '文本质量',
    severity: 'medium',
    enabled: true,
    match_params: { max_chars: threshold },
    prompt,
  };
}

function findTextLongSentenceRule(rules) {
  return rules.find((rule) => rule.rule_id === 'TEXT-LONG-SENTENCE' || rule.rule_id === 'NORM-006');
}

async function seedRuleOverride({ scopeLevel, collegeId = null, rule, updatedBy = 'test-setup' }) {
  await run(
    `INSERT INTO normative_rule_overrides (
       id, scope_level, college_id, rule_id, title, category, severity, enabled, match_params_json, prompt, updated_by, updated_at
     ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
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
      `${scopeLevel}:${collegeId || 'school'}:${rule.rule_id}`,
      scopeLevel,
      collegeId,
      rule.rule_id,
      rule.title,
      rule.category,
      rule.severity,
      rule.enabled ? 1 : 0,
      JSON.stringify(rule.match_params),
      rule.prompt,
      updatedBy,
    ],
  );
}

describe('FLOW-RULE-PUBLISH backend rule configuration contract', () => {
  beforeAll(async () => {
    harness = createTestDatabaseHarness({ label: 'flow-rule-publish', seedDefault: true });
    await harness.setup();
    await seedCollege02Student();
  });

  afterAll(async () => {
    await harness.cleanup();
  });

  it('FLOW-RULE-PUBLISH:API:001 enforces anonymous, denied-role, allowed-role, and cross-college authorization at /api/normative/rule-configs', async () => {
    await request(app)
      .get('/api/normative/rule-configs?level=school')
      .expect(401)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 401 });
        expect(body.rules).toBeUndefined();
      });

    const studentCookie = await login('student01');
    await request(app)
      .get('/api/normative/rule-configs?level=school')
      .set('Cookie', studentCookie)
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
        expect(body.rules).toBeUndefined();
      });

    const schoolCookie = await login('school_admin01');
    await request(app)
      .get('/api/normative/rule-configs?level=school')
      .set('Cookie', schoolCookie)
      .expect(200)
      .expect(({ body }) => {
        expect(body.scope).toMatchObject({ level: 'school' });
        expect(Array.isArray(body.rules)).toBe(true);
      });

    const collegeCookie = await login('college_admin01');
    await request(app)
      .put('/api/normative/rule-configs')
      .set('Cookie', collegeCookie)
      .send({ scope: { level: 'college', college_id: 'college02' }, rule: textLongSentenceRule(90) })
      .expect(403)
      .expect(({ body }) => {
        expect(body).toMatchObject({ code: 403 });
      });
  });

  it('FLOW-RULE-PUBLISH:SCENARIO:001 merges school and college TEXT-LONG-SENTENCE overrides so college01 uses 100 while college02 inherits 120', async () => {
    await publishRuleConfiguration(schoolAdmin, {
      scope: { level: 'school' },
      rule: textLongSentenceRule(120, '学校长句阈值 120'),
    });

    await publishRuleConfiguration(college01Admin, {
      scope: { level: 'college', college_id: 'college01' },
      rule: textLongSentenceRule(100, '学院长句阈值 100'),
    });

    const college01Rules = await resolveRulesForAnalysis({ college_id: 'college01' });
    const college02Rules = await resolveRulesForAnalysis({ college_id: 'college02' });
    const college01Rule = findTextLongSentenceRule(college01Rules);
    const college02Rule = findTextLongSentenceRule(college02Rules);

    expect(college01Rule).toMatchObject({ rule_id: 'TEXT-LONG-SENTENCE', source: 'college' });
    expect(college01Rule.match_params).toMatchObject({ max_chars: 100 });
    expect(college02Rule).toMatchObject({ rule_id: 'TEXT-LONG-SENTENCE', source: 'school' });
    expect(college02Rule.match_params).toMatchObject({ max_chars: 120 });
  });

  it('FLOW-RULE-PUBLISH:SCENARIO:002 rejects college01 admin modifying college02 and leaves college02 persisted rule unchanged', async () => {
    await seedRuleOverride({
      scopeLevel: 'college',
      collegeId: 'college02',
      rule: textLongSentenceRule(120, 'college02 原始阈值'),
    });

    await expect(publishRuleConfiguration(college01Admin, {
      scope: { level: 'college', college_id: 'college02' },
      rule: textLongSentenceRule(80, '非法跨学院修改'),
    })).rejects.toMatchObject({ status: 403 });

    const college02Rules = await listEffectiveRuleConfigurations(schoolAdmin, {
      level: 'college',
      college_id: 'college02',
    });
    const college02Rule = findTextLongSentenceRule(college02Rules.rules);
    const persistedCollege02 = await get(
      `SELECT match_params_json AS matchParamsJson, prompt
         FROM normative_rule_overrides
        WHERE scope_level = 'college' AND college_id = 'college02' AND rule_id = 'TEXT-LONG-SENTENCE'`,
    );

    expect(college02Rule.match_params).toMatchObject({ max_chars: 120 });
    expect(JSON.parse(persistedCollege02.matchParamsJson)).toMatchObject({ max_chars: 120 });
    expect(persistedCollege02.prompt).toBe('college02 原始阈值');
  });

  it('FLOW-RULE-PUBLISH:DB:001 resets only the college override and exposes inherited school rule values', async () => {
    await publishRuleConfiguration(schoolAdmin, {
      scope: { level: 'school' },
      rule: textLongSentenceRule(120, '学校继承阈值'),
    });
    await seedRuleOverride({
      scopeLevel: 'college',
      collegeId: 'college01',
      rule: textLongSentenceRule(100, '待重置学院阈值'),
    });

    const resetResult = await resetCollegeRuleConfiguration(college01Admin, {
      college_id: 'college01',
      rule_id: 'TEXT-LONG-SENTENCE',
    });
    const resetRule = findTextLongSentenceRule(resetResult.rules);
    const remainingCollegeOverride = await get(
      `SELECT id FROM normative_rule_overrides
        WHERE scope_level = 'college' AND college_id = 'college01' AND rule_id = 'TEXT-LONG-SENTENCE'`,
    );
    const schoolOverride = await get(
      `SELECT match_params_json AS matchParamsJson FROM normative_rule_overrides
        WHERE scope_level = 'school' AND rule_id = 'TEXT-LONG-SENTENCE'`,
    );

    expect(resetRule).toMatchObject({ source: 'school' });
    expect(resetRule.match_params).toMatchObject({ max_chars: 120 });
    expect(remainingCollegeOverride).toBeNull();
    expect(JSON.parse(schoolOverride.matchParamsJson)).toMatchObject({ max_chars: 120 });
  });
});
