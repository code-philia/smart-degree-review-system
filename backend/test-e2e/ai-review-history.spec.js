const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AI-REVIEW-HISTORY';
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

async function createCompletedAiReviewRun(page, thesisTitle) {
  const response = await page.request.post('/api/normative/ai-review-runs', {
    data: {
      thesis_title: thesisTitle,
      template_id: 'academic_master',
      text: completedReviewText(),
      source_type: 'paste',
    },
  });
  expect(response.status()).toBe(201);
  const run = await response.json();
  expect(run.id).toEqual(expect.any(String));
  expect(run.user_id).toBe('student01');
  return run;
}

test.describe('FEAT-AI-REVIEW-HISTORY auxiliary review history scenario', () => {
  test('FEAT-AI-REVIEW-HISTORY:SCENARIO:001 student opens history and sees own two records newest first with result entries', async ({ page }) => {
    await loginAsStudent(page);
    const olderRun = await createCompletedAiReviewRun(page, 'student01 较早历史评阅论文');
    const newestRun = await createCompletedAiReviewRun(page, 'student01 最新历史评阅论文');

    await page.goto('/ai-review/history');

    await expect(page.getByRole('heading', { name: 'AI 智能评阅' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '智能评阅记录' })).toBeVisible();
    await expect(page.getByText('共 2 条记录')).toBeVisible();
    const table = page.getByRole('table');
    const rows = table.getByRole('row');
    await expect(rows).toHaveCount(3);

    const newestRow = rows.nth(1);
    const olderRow = rows.nth(2);
    await expect(newestRow).toContainText('student01 最新历史评阅论文');
    await expect(newestRow).toContainText(newestRun.template_id);
    await expect(newestRow).toContainText(String(newestRun.total_score));
    await expect(newestRow).toContainText(newestRun.result_label);
    await expect(newestRow).toContainText(newestRun.created_at.replace('T', ' ').replace('Z', ''));
    await expect(newestRow.getByRole('link', { name: '查看结果' })).toHaveAttribute('href', `/ai-review/results/${newestRun.id}`);

    await expect(olderRow).toContainText('student01 较早历史评阅论文');
    await expect(olderRow).toContainText(olderRun.template_id);
    await expect(olderRow).toContainText(String(olderRun.total_score));
    await expect(olderRow).toContainText(olderRun.result_label);
    await expect(olderRow).toContainText(olderRun.created_at.replace('T', ' ').replace('Z', ''));
    await expect(olderRow.getByRole('link', { name: '查看结果' })).toHaveAttribute('href', `/ai-review/results/${olderRun.id}`);

    const historyResponse = await page.request.get('/api/normative/ai-review-runs');
    expect(historyResponse.status()).toBe(200);
    const historyPayload = await historyResponse.json();
    expect(historyPayload.records.map((record) => record.id)).toEqual([newestRun.id, olderRun.id]);
    expect(historyPayload.records.every((record) => record.user_id === 'student01')).toBe(true);
    expect(historyPayload.records[0].original_text).toBeUndefined();

    await newestRow.getByRole('link', { name: '查看结果' }).click();
    await expect(page).toHaveURL(new RegExp(`/ai-review/results/${newestRun.id}$`));
    await expect(page.getByRole('heading', { name: 'AI 智能评阅报告' })).toBeVisible();
    await expect(page.getByText('student01 最新历史评阅论文')).toBeVisible();
  });
});
