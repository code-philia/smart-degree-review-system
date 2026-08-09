const { test, expect } = require('@playwright/test');
const { run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertInnovationAssessmentSnapshot } = require('../src/normative/innovationAssessmentRepository');

const REQ_ID = 'FEAT-QUALITY-DASHBOARD';
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

async function clearQualityDashboardData() {
  await run("DELETE FROM normative_detection_tasks WHERE user_id IN ('student01', 'student02', 'student03');");
  await run("DELETE FROM duplication_detection_reports WHERE user_id IN ('student01', 'student02', 'student03');");
  await run("DELETE FROM innovation_assessment_snapshots WHERE user_id IN ('student01', 'student02', 'student03');");
  await run("DELETE FROM ai_review_runs WHERE user_id IN ('student01', 'student02', 'student03');");
}

async function seedNormativeRecord(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-规范检测.txt`,
    original_text: '摘要\n正文存在格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: [
      {
        rule_id: 'NORM-001',
        category: '结构',
        severity: 'high',
        line: 1,
        column: 1,
        excerpt: '严重',
        message: '严重错误',
        suggestion: '修改',
      },
      {
        rule_id: 'NORM-002',
        category: '格式',
        severity: 'medium',
        line: 2,
        column: 1,
        excerpt: '一般',
        message: '一般错误',
        suggestion: '修改',
      },
      {
        rule_id: 'NORM-003',
        category: '标点',
        severity: 'low',
        line: 3,
        column: 1,
        excerpt: '轻微',
        message: '轻微错误',
        suggestion: '修改',
      },
    ],
    severity_counts: overrides.severity_counts || {
      high: 1,
      medium: 2,
      low: 3,
    },
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  });
}

async function seedDuplicationRecord(overrides = {}) {
  return createDuplicationHistoryRecord({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-查重检测.txt`,
    original_text: '查重原文内容',
    total_similarity_rate: overrides.total_similarity_rate ?? 0.27,
    writing_risk_score: 66,
    sample_count: 3,
    report_json: { status: 'completed', top_matches: [] },
    created_at: overrides.created_at || '2026-08-04T10:30:00.000Z',
  });
}

async function seedInnovationRecord(overrides = {}) {
  return insertInnovationAssessmentSnapshot({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    thesis_title: '质量仪表盘创新性论文',
    degree_type: 'master',
    primary_discipline: '计算机科学与技术',
    secondary_discipline: '软件工程',
    research_direction: '教育质量分析',
    input_snapshot: { thesis_title: '质量仪表盘创新性论文' },
    scoring_snapshot: {
      total_score: overrides.total_score ?? 88,
      grade_label: '优秀',
      formula: '综合量表分',
      dimensions: [],
      input: {},
    },
    created_at: overrides.created_at || '2026-08-04T11:00:00.000Z',
  });
}

async function prepareScenarioData() {
  await clearQualityDashboardData();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  await seedNormativeRecord({
    id: `quality-dashboard-e2e-normative-${suffix}`,
  });
  await seedDuplicationRecord({
    id: `quality-dashboard-e2e-duplication-${suffix}`,
  });
  await seedInnovationRecord({
    id: `quality-dashboard-e2e-innovation-${suffix}`,
  });
}

test.describe('FEAT-QUALITY-DASHBOARD scenario', () => {
  test('FEAT-QUALITY-DASHBOARD:SCENARIO:001 supervisor sees three computed quality scores and missing review base as 暂无数据', async ({
    page,
  }) => {
    await prepareScenarioData();
    await loginAs(page, 'supervisor01');

    await page.goto('/quality-dashboard');
    await expect(page.getByRole('banner')).toContainText('群体质量仪表盘');

    await expect(page.getByText('样本数').locator('..')).toContainText('1');
    await expect(page.getByText('规范分').locator('..')).toContainText('79.0');
    await expect(page.getByText('原创参考分').locator('..')).toContainText('73.0');
    await expect(page.getByText('创新参考分').locator('..')).toContainText('88.0');
    await expect(page.getByText('评阅基础分').locator('..')).toContainText('暂无数据');
    await expect(page.getByText('评阅基础分').locator('..')).toContainText('有效 0，缺失 1');

    const detailTable = page.getByRole('table');
    await expect(detailTable).toContainText('student01');
    await expect(detailTable).toContainText('79.0');
    await expect(detailTable).toContainText('73.0');
    await expect(detailTable).toContainText('88.0');
    await expect(detailTable).toContainText('暂无数据');
    await expect(detailTable).not.toContainText('0.0');

    const apiResponse = await page.request.get('/api/normative/ledger-records/quality-dashboard');
    expect(apiResponse.status()).toBe(200);
    const body = await apiResponse.json();
    expect(body.sample_count).toBe(1);
    expect(body.metrics).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          key: 'normative',
          average_score: 79,
          sample_count: 1,
        }),
        expect.objectContaining({
          key: 'originality',
          average_score: 73,
          sample_count: 1,
        }),
        expect.objectContaining({
          key: 'innovation',
          average_score: 88,
          sample_count: 1,
        }),
        expect.objectContaining({
          key: 'review_base',
          average_score: null,
          sample_count: 0,
          missing_count: 1,
        }),
      ]),
    );
    expect(body.students[0].scores.review_base).toBeNull();
  });
});
