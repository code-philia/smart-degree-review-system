const { test, expect, open, readyTable, assertLayout, checkA11y } = require('../support.cjs');
test('[live-read] phone public sign-in and trial inputs fit without horizontal page overflow', async ({ page }) => {
  await open(page, '/auth?lang=zh');
  await expect(page.getByRole('link', { name: '使用 jAccount 登录', exact: true })).toBeVisible();
  await assertLayout(page);
  await page.getByRole('button', { name: '上海交通大学校徽', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '试验账号登录', exact: true })).toBeVisible();
  await assertLayout(page);
});
test.describe('phone student', () => {
  test.use({ role: 'student' });
  test('[live-read] expanded rule selection and credits remain in the phone viewport', async ({ page }) => {
    await open(page, '/paper-upload');
    await page.getByRole('button', { name: '展开选择', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: /^关键词数量/ })).toBeVisible();
    await assertLayout(page);
  });
  test('[live-read] feedback dialog can be read and dismissed on a phone', async ({ page }) => {
    await open(page, '/paper-upload'); await page.getByRole('button', { name: '使用反馈', exact: true }).click();
    const dialog = page.getByRole('dialog'); await expect(dialog).toBeVisible();
    await dialog.getByRole('button', { name: '取消', exact: true }).click();
    await expect(dialog).not.toBeVisible(); await assertLayout(page);
  });
});
test.describe('phone administrator', () => {
  test.use({ role: 'admin' });
  for (const [route, table] of [['/admin/reports', '全部用户检测报告'], ['/admin/feedback', '全部用户反馈']]) test(`[live-read] ${route} contains wide tables inside a locally scrollable region`, async ({ page }) => {
    await open(page, route); await readyTable(page, table);
    await assertLayout(page);
    const scroll = page.locator('.sup-table-scroll');
    expect(await scroll.evaluate(e => getComputedStyle(e).overflowX)).toBe('auto');
  });
});
