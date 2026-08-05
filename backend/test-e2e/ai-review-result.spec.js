const { readFile } = require('node:fs/promises');
const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AI-REVIEW-RESULT';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAsStudent(page) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(/已登录：student01（STUDENT）/)).toBeVisible();
}

function buildReferenceLines(count) {
  return Array.from({ length: count }, (_, index) => `[${index + 1}] 引用条目 ${index + 1}`).join('\n');
}

function completedReviewText(referenceCount = 50) {
  return [
    '摘要',
    '关键词',
    '引言',
    '研究方法',
    '分析与讨论',
    '结论',
    '参考文献',
    buildReferenceLines(referenceCount),
  ].join('\n');
}

async function createCompletedAiReviewRun(page) {
  const payload = {
    thesis_title: '辅助评阅结果验证论文',
    template_id: 'academic_master',
    text: completedReviewText(),
    source_type: 'paste',
  };

  const response = await page.request.post('/api/normative/ai-review-runs', { data: payload });
  expect(response.status()).toBe(201);
  const run = await response.json();
  expect(run.id).toEqual(expect.any(String));
  expect(run.score_items).toHaveLength(5);
  return { payload, run };
}

test.describe('FEAT-AI-REVIEW-RESULT auxiliary review result scenario', () => {
  test('FEAT-AI-REVIEW-RESULT:SCENARIO:001 student opens a completed result where five objective scores equal total and subjective dimensions await human confirmation', async ({ page }) => {
    await loginAsStudent(page);
    const { payload, run } = await createCompletedAiReviewRun(page);
    const expectedScoreTotal = run.score_items.reduce((sum, item) => sum + Number(item.score), 0);

    await page.goto(`/ai-review/results/${run.id}`);

    await expect(page.getByRole('heading', { name: 'AI 智能评阅报告' })).toBeVisible();
    await expect(page.getByText('论文预览')).toBeVisible();
    await expect(page.getByText(payload.thesis_title)).toBeVisible();
    await expect(page.getByTestId('ai-review-result-source-preview')).toContainText('1');
    await expect(page.getByTestId('ai-review-result-source-preview')).toContainText('摘要');
    await expect(page.getByTestId('ai-review-result-basic-info')).toContainText(payload.template_id);
    await expect(page.getByTestId('ai-review-result-basic-info')).toContainText(run.result_label);

    const scoreTable = page.getByRole('table', { name: '五项客观评分' });
    await expect(scoreTable).toBeVisible();
    for (const item of run.score_items) {
      await expect(scoreTable).toContainText(item.label);
      await expect(scoreTable).toContainText(String(item.score));
    }
    await expect(page.getByTestId('ai-review-result-score-sum')).toContainText(String(expectedScoreTotal));
    await expect(page.getByTestId('ai-review-result-total-score')).toContainText(String(run.total_score));
    expect(expectedScoreTotal).toBe(run.total_score);

    const apiResponse = await page.request.get(`/api/normative/ai-review-runs/${run.id}`);
    expect(apiResponse.status()).toBe(200);
    const detail = await apiResponse.json();
    expect(detail.score_items).toHaveLength(5);
    expect(detail.objective_score_total).toBe(detail.total_score);
    expect(detail.subjective_confirmation_items.every((item) => item.status === '待人工确认')).toBe(true);

    const subjectiveList = page.getByTestId('ai-review-result-subjective-confirmations');
    await expect(subjectiveList).toBeVisible();
    for (const item of detail.subjective_confirmation_items) {
      await expect(subjectiveList).toContainText(item.label);
      await expect(subjectiveList).toContainText('待人工确认');
    }

    await expect(page.getByRole('button', { name: '浏览器打印' })).toBeVisible();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /下载 JSON|下载评阅报告/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`ai-review-result-${run.id}.json`);
    const downloadPath = await download.path();
    if (!downloadPath) {
      throw new Error('Downloaded AI review result JSON file path was not available');
    }
    const downloadedPayload = JSON.parse(await readFile(downloadPath, 'utf8'));
    expect(downloadedPayload.report_type).toBe('ai_review_result');
    expect(downloadedPayload.result.id).toBe(run.id);
    expect(downloadedPayload.result.objective_score_total).toBe(run.total_score);
    expect(downloadedPayload.result.subjective_confirmation_items.every((item) => item.status === '待人工确认')).toBe(true);
  });
});
