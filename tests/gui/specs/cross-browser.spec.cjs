const { test, expect, open, readyTable, assertLayout } = require('../support.cjs');
test('[live-read] cross-engine public Chinese/English sign-in and native trial dialog', async ({ page }) => {
  await open(page, '/auth?lang=zh');
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '上海交通大学校徽', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '试验账号登录', exact: true })).toBeVisible();
  await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.getByRole('button', { name: 'EN', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Sign in with jAccount', exact: true })).toBeVisible();
  await assertLayout(page);
});
test.describe('student engine compatibility', () => {
  test.use({ role: 'student' });
  test('[live-read] upload catalog, credits and free selection are usable', async ({ page }) => {
    await open(page, '/paper-upload');
    await page.getByRole('button', { name: '展开选择', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: /^关键词数量/ })).toBeChecked();
    await expect(page.getByRole('button', { name: /可用额度 .*查看额度说明/ })).toBeEnabled();
    await page.getByRole('button', { name: '清空全部检测规则', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: /^关键词数量/ })).not.toBeChecked();
    await assertLayout(page);
  });
  test('[live-read] saved history can search and recover without navigation errors', async ({ page }) => {
    await open(page, '/reports');
    const input = page.getByRole('searchbox', { name: '搜索检测报告', exact: true });
    await input.fill('GUI_TEST_NO_SUCH_RECORD_829346');
    await expect(page.getByText(/未找到|没有找到|无匹配/).first()).toBeVisible();
    await input.fill(''); await expect(page.getByRole('table', { name: '规范性检测报告', exact: true })).toBeVisible();
  });
});
test.describe('administrator engine compatibility', () => {
  test.use({ role: 'admin' });
  test('[live-read] admin table/search/type dropdown are compatible', async ({ page }) => {
    await open(page, '/admin/reports'); await readyTable(page, '全部用户检测报告');
    const filtered = page.waitForResponse(response => {
      const target = new URL(response.url());
      return response.request().method() === 'GET' && target.pathname === '/api/supervision/reports' && target.searchParams.get('type') === 'duplication';
    });
    await page.getByLabel('报告类型', { exact: true }).selectOption('duplication');
    await filtered;
    await readyTable(page, '全部用户检测报告');
    await expect(page.getByRole('table', { name: '全部用户检测报告' })).toContainText('查重检测');
    await assertLayout(page);
  });
  test('[live-read] admin light/dark mode persists through reload', async ({ page }) => {
    await open(page, '/admin/reports');
    await page.getByRole('button', { name: '切换到深色模式', exact: true }).click();
    await expect(page.locator('html')).toHaveClass(/dark/);
    await page.reload(); await readyTable(page, '全部用户检测报告');
    await expect(page.locator('html')).toHaveClass(/dark/);
  });
});
