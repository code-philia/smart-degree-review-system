const { test, expect } = require('@playwright/test');
const { run } = require('../src/database');
const { createDetectionTask } = require('../src/normative/detectionTaskRepository');
const { createDuplicationHistoryRecord } = require('../src/normative/duplicationHistoryRepository');
const { insertInnovationAssessmentSnapshot } = require('../src/normative/innovationAssessmentRepository');
const { insertAiReviewRun } = require('../src/normative/aiReviewRunRepository');

const REQ_ID = 'FEAT-STUDENT-QUALITY-PORTRAIT';
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

async function clearStudentQualityPortraitData() {
  await run("DELETE FROM normative_detection_tasks WHERE user_id IN ('student01', 'student02');");
  await run("DELETE FROM duplication_detection_reports WHERE user_id IN ('student01', 'student02');");
  await run("DELETE FROM innovation_assessment_snapshots WHERE user_id IN ('student01', 'student02');");
  await run("DELETE FROM ai_review_runs WHERE user_id IN ('student01', 'student02');");
}

async function seedNormativeRecord(overrides = {}) {
  return createDetectionTask({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    status: 'completed',
    source_type: 'file',
    source_filename: `${overrides.user_id || 'student01'}-规范检测.txt`,
    original_text: '摘要\n正文存在格式问题。',
    rule_snapshot: [{ rule_id: 'NORM-001', title: '规范检测模板' }],
    issues: [],
    severity_counts: overrides.severity_counts || { high: 2, medium: 0, low: 0 },
    created_at: overrides.created_at || '2026-08-04T10:00:00.000Z',
  });
}

async function seedDuplicationRecord(overrides = {}) {
  return createDuplicationHistoryRecord({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    source_type: 'file',
    source_filename: `${overrides.user_id || 'student01'}-查重检测.txt`,
    original_text: '查重原文内容',
    total_similarity_rate: overrides.total_similarity_rate ?? 0.1,
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
    thesis_title: '单学生本地质量画像研究',
    degree_type: 'master',
    primary_discipline: '计算机科学与技术',
    secondary_discipline: '软件工程',
    research_direction: '教育质量分析',
    input_snapshot: { thesis_title: '单学生本地质量画像研究' },
    scoring_snapshot: {
      total_score: overrides.total_score ?? 70,
      grade_label: '合格',
      formula: '综合量表分',
      dimensions: [],
      input: {},
    },
    created_at: overrides.created_at || '2026-08-04T11:00:00.000Z',
  });
}

async function seedAiReviewRecord(overrides = {}) {
  return insertAiReviewRun({
    id: overrides.id,
    user_id: overrides.user_id || 'student01',
    thesis_title: '单学生本地质量画像研究',
    template_id: 'academic_master',
    source_type: 'file',
    source_filename: `${overrides.user_id || 'student01'}-AI评阅.txt`,
    original_text: '摘要\n关键词\n正文\n结论\n参考文献',
    section_snapshot: [],
    reference_count: 12,
    character_count: 120,
    normative_issues: [],
    score_items: [],
    total_score: overrides.total_score ?? 80,
    result_label: '基础检查通过',
    missing_sections: [],
    rubric_snapshot: { template: { template_id: 'academic_master', name: '学术型硕士' } },
    created_at: overrides.created_at || '2026-08-04T11:30:00.000Z',
  });
}

async function prepareCompleteScenarioData() {
  await clearStudentQualityPortraitData();
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  await seedNormativeRecord({ id: `student-quality-portrait-e2e-normative-${suffix}`, severity_counts: { high: 2, medium: 0, low: 0 } });
  await seedDuplicationRecord({ id: `student-quality-portrait-e2e-duplication-${suffix}`, total_similarity_rate: 0.1 });
  await seedInnovationRecord({ id: `student-quality-portrait-e2e-innovation-${suffix}`, total_score: 70 });
  await seedAiReviewRecord({ id: `student-quality-portrait-e2e-review-${suffix}`, total_score: 80 });
}

test.describe('FEAT-STUDENT-QUALITY-PORTRAIT scenarios', () => {
  test('FEAT-STUDENT-QUALITY-PORTRAIT:SCENARIO:001 student sees four latest source metrics and 80 comprehensive score', async ({ page }) => {
    await prepareCompleteScenarioData();
    await loginAs(page, 'student01');

    await page.goto('/student-quality-portrait/student01');
    await expect(page.getByRole('banner')).toContainText('单学生本地质量画像');
    await page.getByRole('button', { name: '查询' }).click();

    await expect(page.getByText('单学生论文全景质量画像')).toBeVisible();
    await expect(page.getByText('综合分').locator('..')).toContainText('80.0 分');
    await expect(page.getByText('规范分').locator('..')).toContainText('80.0');
    await expect(page.getByText('原创参考分').locator('..')).toContainText('90.0');
    await expect(page.getByText('创新参考分').locator('..')).toContainText('70.0');
    await expect(page.getByText('评阅基础分').locator('..')).toContainText('80.0');
    await expect(page.getByText('规范分').locator('..')).toContainText('2026-08-04T10:00:00.000Z');
    await expect(page.getByText('原创参考分').locator('..')).toContainText('2026-08-04T10:30:00.000Z');
    await expect(page.getByText('创新参考分').locator('..')).toContainText('2026-08-04T11:00:00.000Z');
    await expect(page.getByText('评阅基础分').locator('..')).toContainText('2026-08-04T11:30:00.000Z');
    await expect(page.getByRole('link', { name: '查看详情' })).toHaveCount(4);

    const apiResponse = await page.request.get('/api/normative/ledger-records/student-quality-portrait/student01');
    expect(apiResponse.status()).toBe(200);
    const body = await apiResponse.json();
    expect(body.overall_score).toBe(80);
    expect(body.completeness.complete).toBe(true);
    expect(body.metrics).toEqual(expect.arrayContaining([
      expect.objectContaining({ key: 'normative', score: 80 }),
      expect.objectContaining({ key: 'originality', score: 90 }),
      expect.objectContaining({ key: 'innovation', score: 70 }),
      expect.objectContaining({ key: 'review_base', score: 80 }),
    ]));
  });

  test('FEAT-STUDENT-QUALITY-PORTRAIT:SCENARIO:002 backend returns 403 and no metrics when student requests another student portrait id', async ({ page }) => {
    await prepareCompleteScenarioData();
    await loginAs(page, 'student01');

    const response = await page.request.get('/api/normative/ledger-records/student-quality-portrait/student02');
    expect(response.status()).toBe(403);
    const body = await response.json();
    expect(body).toMatchObject({ code: 403 });
    expect(body.metrics).toBeUndefined();
    expect(JSON.stringify(body)).not.toContain('normative');
    expect(JSON.stringify(body)).not.toContain('originality');
    expect(JSON.stringify(body)).not.toContain('innovation');
    expect(JSON.stringify(body)).not.toContain('review_base');
  });
});
