const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AI-REVIEW-RUBRICS';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAsStudent(page) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText('已登录：student01（STUDENT）')).toBeVisible();
}

test.describe('FEAT-AI-REVIEW-RUBRICS auxiliary review rubric scenario', () => {
  test('FEAT-AI-REVIEW-RUBRICS:SCENARIO:001 student opens template selector and sees five templates with required sections, minimum references, and shared scoring items', async ({ page }) => {
    await loginAsStudent(page);

    await page.goto('/normative-check');
    await expect(page.getByRole('heading', { name: '文档上传' })).toBeVisible();
    await expect(page.getByText('展示内置五类评阅模板、必需章节、最低文献数和共享计分项')).toBeVisible();

    await page.getByRole('button', { name: '打开模板选择器' }).click();

    await expect(page.getByText('学术型博士自然科学')).toBeVisible();
    await expect(page.getByText('学术型博士人文社科')).toBeVisible();
    await expect(page.getByText('专业型博士')).toBeVisible();
    await expect(page.getByText('学术型硕士')).toBeVisible();
    await expect(page.getByText('专业型硕士')).toBeVisible();

    const firstTemplate = page.getByText('学术型博士自然科学').locator('..');
    await expect(firstTemplate.getByText('最低参考文献数量：80')).toBeVisible();
    await expect(firstTemplate.getByText('研究方法')).toBeVisible();
    await expect(firstTemplate.getByText('结论')).toBeVisible();
    await expect(firstTemplate.getByText('参考文献')).toBeVisible();

    const scoringSection = page.getByRole('heading', { name: '共享客观计分项' }).locator('..');
    await expect(scoringSection.getByText('章节完整性')).toBeVisible();
    await expect(scoringSection.getByText('参考文献数量与编号')).toBeVisible();
    await expect(scoringSection.getByText('研究方法章节')).toBeVisible();
    await expect(scoringSection.getByText('结论章节')).toBeVisible();
    await expect(scoringSection.getByText('规范检测结果')).toBeVisible();
    await expect(scoringSection.getByText('30 分')).toBeVisible();
    await expect(scoringSection.getByText('20 分')).toHaveCount(3);
    await expect(scoringSection.getByText('10 分')).toBeVisible();
    await expect(scoringSection.getByText(/客观分不低于 80 且无必需章节缺失时为“基础检查通过”，否则为“需修改”。/)).toBeVisible();

    const apiResponse = await page.request.get('/api/normative/review-rubrics');
    expect(apiResponse.status()).toBe(200);
    const apiBody = await apiResponse.json();
    expect(apiBody.templates).toHaveLength(5);
    expect(apiBody.shared_score_items.map((item) => item.points)).toEqual([30, 20, 20, 20, 10]);
    expect(apiBody.passing_rule.pass_label).toBe('基础检查通过');
    expect(apiBody.passing_rule.revise_label).toBe('需修改');
  });
});
