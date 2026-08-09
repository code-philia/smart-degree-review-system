const { test, expect } = require('@playwright/test');
const { seedDemoDatabase } = require('../src/database/seed_demo_db');

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await page.getByRole('textbox', { name: '账号', exact: true }).fill(username);
  await page.getByLabel('密码', { exact: true }).fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: `欢迎回来，${username}` })).toBeVisible();
}

async function logout(page, username) {
  await page.getByRole('button', { name: new RegExp(username) }).click();
  await page.getByRole('menuitem', { name: '退出登录' }).click();
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
}

test.beforeAll(async () => {
  await seedDemoDatabase({ confirmDemoData: true });
});

test.describe('four-role demo data walkthrough', () => {
  test('student and supervisor can demonstrate the complete review workflow', async ({ page }) => {
    await loginAs(page, 'student01');
    await page.goto('/');
    await expect(page.getByText(/有 1 份报告已收到导师反馈/)).toBeVisible();

    await page.goto('/normative-reports');
    await expect(page.locator('tbody tr')).toHaveCount(5);
    await expect(page.getByText('高校数字治理质量评价体系研究_预答辩稿.pdf')).toBeVisible();

    await page.goto('/duplication-history');
    await expect(page.locator('tbody tr')).toHaveCount(5);

    await page.goto('/innovation-history');
    await expect(page.locator('tbody tr')).toHaveCount(5);

    await page.goto('/ai-review/history');
    await expect(page.locator('tbody tr')).toHaveCount(5);

    await page.goto('/polish-history');
    await expect(page.getByText(/共 5 条记录/)).toBeVisible();
    await expect(page.getByText('高校数字治理质量评价体系研究_语言修改稿.docx')).toBeVisible();
    await expect(page.getByRole('cell', { name: '局部润色' }).first()).toBeVisible();

    await page.goto('/student-report-results');
    await expect(page.getByText('共 5 条')).toBeVisible();
    await expect(page.getByText('等待导师批阅')).toBeVisible();
    await expect(page.getByRole('link', { name: '查看详情' })).toHaveCount(4);

    await logout(page, 'student01');
    await loginAs(page, 'supervisor01');
    await page.goto('/');
    await expect(page.getByText(/共有 1 条待批阅任务/)).toBeVisible();

    await page.goto('/supervisor-review-queue');
    const pendingRow = page.getByRole('row').filter({ hasText: '第三轮待批阅' });
    await expect(pendingRow).toContainText('待批阅');
    await pendingRow.getByRole('link', { name: '批阅' }).click();
    await expect(page.getByText('finding-norm-001')).toBeVisible();
    await expect(page.getByText(/该句信息较集中/)).toBeVisible();
  });

  test('college and school admins see scoped ledgers and populated management pages', async ({ page }) => {
    await loginAs(page, 'college_admin01');
    await page.goto('/');
    await expect(page.getByText('学院记录数').locator('..')).toContainText('27');
    await expect(page.getByText('覆盖学生数').locator('..')).toContainText('5');

    await page.goto('/quality-dashboard');
    await expect(page.getByText('样本数').locator('..')).toContainText('5');
    await expect(page.getByRole('table')).toContainText('student01');

    await logout(page, 'college_admin01');
    await loginAs(page, 'school_admin01');
    await page.goto('/');
    await expect(page.getByText('全校记录数').locator('..')).toContainText('36');
    await expect(page.getByText('覆盖学生数').locator('..')).toContainText('8');

    await page.goto('/duplication-corpus');
    await expect(page.getByText('高校数字治理与质量保障案例样本')).toBeVisible();
    await expect(page.getByText('研究生学术写作规范案例样本')).toBeVisible();
    await expect(page.getByText('生成式人工智能教育应用案例样本')).toBeVisible();
    await expect(page.getByText('研究生培养过程评价与反馈机制研究')).toBeVisible();
    await expect(page.getByText('高校科研诚信教育实施路径案例')).toBeVisible();

    await page.goto('/quality-dashboard');
    await expect(page.getByText('样本数').locator('..')).toContainText('8');
  });
});
