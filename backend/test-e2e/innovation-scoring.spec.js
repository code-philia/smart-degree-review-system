const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-INNOVATION-SCORING-MODEL';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAsStudent(page) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByRole('textbox', { name: '账号' }).fill('student01');
  await page.getByRole('textbox', { name: '密码' }).fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByRole('heading', { name: '欢迎回来，student01' })).toBeVisible();
}

test.describe('FEAT-INNOVATION-SCORING-MODEL innovation scoring scenario', () => {
  test('FEAT-INNOVATION-SCORING-MODEL:SCENARIO:001 calculates master levels 5,4,4,3,4 as 80 and 良好', async ({ page }) => {
    await loginAsStudent(page);

    await page.goto('/innovation-scoring');
    await expect(page.getByRole('heading', { name: '创新性评分' })).toBeVisible();
    await expect(page.getByText('当前账号：student01')).toBeVisible();
    await expect(page.getByRole('radio', { name: /硕士/ })).toBeChecked();

    await page.getByLabel('研究选题等级').selectOption('5');
    await page.getByLabel('研究方法等级').selectOption('4');
    await page.getByLabel('研究内容等级').selectOption('4');
    await page.getByLabel('研究结论等级').selectOption('3');
    await page.getByLabel('应用价值等级').selectOption('4');
    await page.getByRole('button', { name: '计算创新性分数' }).click();

    await expect(page.getByRole('heading', { name: '创新性评分报告' })).toBeVisible();
    await expect(page.getByText('80 分')).toBeVisible();
    await expect(page.getByText('良好')).toBeVisible();
    await expect(page.getByText(/维度原始分=等级×20/)).toBeVisible();
    await expect(page.getByText(/综合分=各维度原始分×权重之和/)).toBeVisible();
    await expect(page.getByText(/硕士权重依次为 20%、20%、25%、20%、15%/)).toBeVisible();

    const table = page.getByRole('table', { name: '创新性评分明细' });
    await expect(table.getByText('研究选题')).toBeVisible();
    await expect(table.getByText('研究方法')).toBeVisible();
    await expect(table.getByText('研究内容')).toBeVisible();
    await expect(table.getByText('研究结论')).toBeVisible();
    await expect(table.getByText('应用价值')).toBeVisible();
    await expect(table.getByText('100')).toBeVisible();
    await expect(table.getByText('25%')).toBeVisible();
    await expect(table.getByText('15%')).toBeVisible();
  });

  test('FEAT-INNOVATION-SCORING-MODEL anonymous users see login-required state on the page route', async ({ page }) => {
    await page.goto('/innovation-scoring');

    await expect(page.getByRole('heading', { name: '创新性评分' })).toBeVisible();
    await expect(page.getByText(/请先登录后计算创新性分数/)).toBeVisible();
    await expect(page.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
  });
});
