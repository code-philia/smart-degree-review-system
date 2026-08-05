const { test, expect } = require('@playwright/test');
const { run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');

const REQ_ID = 'FEAT-LEDGER-FILTERED-STATS';
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
    issues: [{ rule_id: 'NORM-001', category: '标点配对', severity: 'high', line: 1, column: 1, excerpt: '问题片段', message: '格式问题', suggestion: '修订格式' }],
    severity_counts: { high: 1, medium: 0, low: 0 },
    created_at: overrides.created_at || '2026-08-01T08:00:00.000Z',
  });
}

async function seedDuplicationRecord(overrides = {}) {
  return createDuplicationHistoryRecord({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    source_type: 'file',
    source_filename: overrides.source_filename || `${overrides.user_id || 'student01'}-查重检测.txt`,
    original_text: '查重原文内容',
    total_similarity_rate: 0.37,
    writing_risk_score: 66,
    sample_count: 3,
    report_json: { status: 'completed', top_matches: [] },
    created_at: overrides.created_at || '2026-08-02T11:00:00.000Z',
  });
}

async function prepareFilteredStatsData() {
  await run('DELETE FROM normative_detection_tasks WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await run('DELETE FROM duplication_detection_reports WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await run('DELETE FROM innovation_assessment_snapshots WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await run('DELETE FROM ai_review_runs WHERE user_id IN (\'student01\', \'student02\', \'student03\');');
  await seedLedgerUsers();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;

  await seedNormativeRecord({
    id: `ledger-stats-e2e-college01-norm-aug01-${suffix}`,
    user_id: 'student01',
    source_filename: `college01-规范检测-8月1日-${suffix}.txt`,
    created_at: '2026-08-01T08:00:00.000Z',
  });
  await seedNormativeRecord({
    id: `ledger-stats-e2e-college01-norm-aug02-${suffix}`,
    user_id: 'student02',
    source_filename: `college01-规范检测-8月2日-${suffix}.txt`,
    created_at: '2026-08-02T09:00:00.000Z',
  });
  await seedNormativeRecord({
    id: `ledger-stats-e2e-college01-norm-out-of-range-${suffix}`,
    user_id: 'student01',
    source_filename: `college01-规范检测-范围外-${suffix}.txt`,
    created_at: '2026-08-05T09:00:00.000Z',
  });
  await seedNormativeRecord({
    id: `ledger-stats-e2e-college02-hidden-${suffix}`,
    user_id: 'student03',
    source_filename: `college02-不应统计规范检测-${suffix}.txt`,
    created_at: '2026-08-02T10:00:00.000Z',
  });
  await seedDuplicationRecord({
    id: `ledger-stats-e2e-college01-dup-hidden-${suffix}`,
    user_id: 'student01',
    source_filename: `college01-不应统计查重检测-${suffix}.txt`,
    created_at: '2026-08-02T11:00:00.000Z',
  });
}

test.describe('FEAT-LEDGER-FILTERED-STATS scenario', () => {
  test('FEAT-LEDGER-FILTERED-STATS:SCENARIO:001 college admin refresh recalculates table and local charts from filtered college01 normative records', async ({ page }) => {
    await prepareFilteredStatsData();
    await loginAs(page, 'college_admin01');

    await page.goto('/ledger-stats');
    await expect(page.getByRole('heading', { name: '筛选统计与本地图表' })).toBeVisible();
    await expect(page.getByText('请选择条件后生成图表')).toBeVisible();

    await page.getByLabel('检测类型').selectOption('normative');
    await page.getByLabel('开始日期').fill('2026-08-01');
    await page.getByLabel('结束日期').fill('2026-08-02');
    await page.getByRole('button', { name: '生成图表' }).click();

    await expect(page.getByTestId('ledger-stats-total-records')).toHaveText(/2/);
    await expect(page.getByTestId('ledger-stats-total-students')).toHaveText(/2/);
    await expect(page.getByTestId('ledger-stats-active-type')).toContainText('规范检测');

    const statsTable = page.getByTestId('ledger-stats-table');
    await expect(statsTable).toContainText('规范检测');
    await expect(statsTable).toContainText('2');
    await expect(statsTable).not.toContainText('校内库查重');
    await expect(statsTable).not.toContainText('college02');

    const barChart = page.getByTestId('ledger-stats-type-bar-chart');
    await expect(barChart).toContainText('规范检测');
    await expect(barChart.locator('[data-chart-bar="normative"]')).toHaveCount(1);

    const trendChart = page.getByTestId('ledger-stats-daily-trend-chart');
    await expect(trendChart.locator('svg')).toHaveCount(1);
    await expect(trendChart).toContainText('2026-08-01');
    await expect(trendChart).toContainText('2026-08-02');
    await expect(trendChart).not.toContainText('2026-08-05');

    const apiResponse = await page.request.get('/api/normative/ledger-records/stats', {
      params: {
        detection_type: 'normative',
        from: '2026-08-01',
        to: '2026-08-02',
        latest_only: 'false',
      },
    });
    expect(apiResponse.status()).toBe(200);
    const body = await apiResponse.json();
    expect(body.total_records).toBe(2);
    expect(body.total_students).toBe(2);
    expect(body.by_type).toEqual([
      expect.objectContaining({ detection_type: 'normative', total_records: 2 }),
    ]);
  });
});
