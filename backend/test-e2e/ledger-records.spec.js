const { test, expect } = require('@playwright/test');
const { run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertInnovationAssessmentSnapshot } = require('../src/normative/innovationAssessmentRepository');
const { insertAiReviewRun } = require('../src/normative/aiReviewRunRepository');

const REQ_ID = 'FEAT-LEDGER-RECORDS';
void REQ_ID;

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

async function seedLedgerUsers() {
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student02', 'student02', password_hash, 'STUDENT', 'college01', 'supervisor02', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'student03', 'student03', password_hash, 'STUDENT', 'college02', 'supervisor03', 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'supervisor02', 'supervisor02', password_hash, 'SUPERVISOR', 'college01', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
  await run(
    `INSERT INTO auth_users (id, username, password_hash, role, college_id, supervisor_id, scope)
     SELECT 'college_admin02', 'college_admin02', password_hash, 'COLLEGE_ADMIN', 'college02', NULL, 'COLLEGE'
       FROM auth_users WHERE username = 'student01'
     ON CONFLICT(username) DO UPDATE SET role = excluded.role, college_id = excluded.college_id, supervisor_id = excluded.supervisor_id`,
  );
}

async function seedLedgerRecords(suffix) {
  const ids = {
    ownedNewest: `ledger-e2e-supervisor-owned-new-${suffix}`,
    ownedOlder: `ledger-e2e-supervisor-owned-old-${suffix}`,
    hidden: `ledger-e2e-non-owned-hidden-${suffix}`,
    hiddenCollege: `ledger-e2e-innovation-hidden-${suffix}`,
  };

  await createDetectionTask({
    id: ids.ownedNewest,
    user_id: 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: `supervisor01-最新规范检测-${suffix}.txt`,
    original_text: '正文存在格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: [{ rule_id: 'NORM-001', category: '标点配对', severity: 'high', line: 1, column: 1, excerpt: '问题片段', message: '格式问题', suggestion: '修订格式' }],
    severity_counts: { high: 1, medium: 0, low: 0 },
    created_at: '2026-08-05T10:00:00.000Z',
  });
  await createDetectionTask({
    id: ids.ownedOlder,
    user_id: 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: `supervisor01-旧规范检测-${suffix}.txt`,
    original_text: '正文存在较早的格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: [{ rule_id: 'NORM-001', category: '标点配对', severity: 'high', line: 1, column: 1, excerpt: '问题片段', message: '格式问题', suggestion: '修订格式' }],
    severity_counts: { high: 1, medium: 0, low: 0 },
    created_at: '2026-08-04T10:00:00.000Z',
  });
  await createDetectionTask({
    id: ids.hidden,
    user_id: 'student02',
    status: 'completed',
    source_type: 'file',
    source_filename: `supervisor02-不应出现规范检测-${suffix}.txt`,
    original_text: '非名下学生记录。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: [{ rule_id: 'NORM-001', category: '标点配对', severity: 'high', line: 1, column: 1, excerpt: '问题片段', message: '格式问题', suggestion: '修订格式' }],
    severity_counts: { high: 1, medium: 0, low: 0 },
    created_at: '2026-08-06T10:00:00.000Z',
  });
  await createDuplicationHistoryRecord({
    id: `ledger-e2e-duplication-own-${suffix}`,
    user_id: 'student01',
    source_type: 'file',
    source_filename: `student01-查重记录-${suffix}.txt`,
    original_text: '查重原文内容',
    total_similarity_rate: 0.37,
    writing_risk_score: 66,
    sample_count: 3,
    report_json: { status: 'completed', top_matches: [] },
    created_at: '2026-08-06T11:00:00.000Z',
  });
  await insertInnovationAssessmentSnapshot({
    id: ids.hiddenCollege,
    user_id: 'student03',
    thesis_title: `college02 隐藏创新报告-${suffix}`,
    degree_type: 'master',
    primary_discipline: '管理学',
    secondary_discipline: '公共管理',
    research_direction: '高校数字治理',
    input_snapshot: { dimensions: {} },
    scoring_snapshot: { total_score: 81, grade_label: '良好', dimensions: [], formula: 'sum' },
    created_at: '2026-08-06T12:00:00.000Z',
  });
  await insertAiReviewRun({
    id: `ledger-e2e-ai-review-own-${suffix}`,
    user_id: 'student01',
    thesis_title: `student01 AI 评阅台账记录-${suffix}`,
    template_id: 'academic_master',
    source_type: 'paste',
    source_filename: null,
    original_text: '摘要\n关键词\n引言\n结论\n参考文献\n[1] 示例',
    section_snapshot: [],
    reference_count: 1,
    character_count: 30,
    normative_issues: [],
    score_items: [],
    total_score: 91,
    result_label: '基础检查通过',
    missing_sections: [],
    rubric_snapshot: {},
    created_at: '2026-08-06T13:00:00.000Z',
  });

  return ids;
}

async function prepareLedgerData() {
  await run('DELETE FROM normative_detection_tasks WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await run('DELETE FROM duplication_detection_reports WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await run('DELETE FROM innovation_assessment_snapshots WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await run('DELETE FROM ai_review_runs WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await seedLedgerUsers();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  return seedLedgerRecords(suffix);
}

test.describe('FEAT-LEDGER-RECORDS role-scoped ledger scenarios', () => {
  test('FEAT-LEDGER-RECORDS:SCENARIO:001 supervisor only sees owned student records on the page and in exported CSV', async ({ page }) => {
    const ids = await prepareLedgerData();
    await loginAs(page, 'supervisor01');

    await page.goto('/ledger-records');
    await expect(page.getByText('学位论文检测台账管理')).toBeVisible();
    await expect(page.getByRole('button', { name: '查询' })).toBeVisible();
    await expect(page.getByRole('button', { name: '导出' })).toBeVisible();

    await page.getByLabel('学生').fill('student01');
    await page.getByRole('button', { name: '查询' }).click();
    await expect(page.getByText('共 2 条记录，已选择 0 条')).toBeVisible();

    const table = page.getByRole('table');
    await expect(table).toContainText('supervisor01-最新规范检测');
    await expect(table).toContainText('supervisor01-旧规范检测');
    await expect(table.getByText('supervisor02-不应出现规范检测')).toHaveCount(0);
    await expect(table.getByText('college02 隐藏创新报告')).toHaveCount(0);

    await page.getByRole('button', { name: '校内库查重' }).click();
    await page.getByRole('button', { name: '查询' }).click();
    await expect(page.getByText('共 1 条记录，已选择 0 条')).toBeVisible();
    await expect(table).toContainText('student01-查重记录');

    await page.getByRole('button', { name: 'AI智能评阅' }).click();
    await page.getByRole('button', { name: '查询' }).click();
    await expect(page.getByText('共 1 条记录，已选择 0 条')).toBeVisible();
    await expect(table).toContainText('student01 AI 评阅台账记录');

    const exportResponse = await page.request.get('/api/normative/ledger-records/export.csv', {
      params: {
        student: 'student01',
        detection_type: 'ai_review',
        latest_only: 'false',
      },
    });
    expect(exportResponse.status()).toBe(200);
    const csvText = await exportResponse.text();
    expect(csvText.charCodeAt(0)).toBe(0xfeff);
    expect(csvText).toContain('student01 AI 评阅台账记录');
    expect(csvText).toContain('student01');
    expect(csvText).not.toContain('supervisor02-不应出现规范检测');
    expect(csvText).not.toContain('college02 隐藏创新报告');
    expect(ids.hiddenCollege).toBeTruthy();
  });

  test('FEAT-LEDGER-RECORDS:SCENARIO:002 college admin receives 403 when requesting a record outside their college scope', async ({ page }) => {
    await prepareLedgerData();
    await loginAs(page, 'college_admin01');

    const forbiddenResponse = await page.request.get('/api/normative/ledger-records/ledger-e2e-innovation-hidden');
    expect(forbiddenResponse.status()).toBe(403);
    const body = await forbiddenResponse.text();
    expect(body).not.toContain('college02 隐藏创新报告');
    expect(body).not.toContain('college02');
  });
});
