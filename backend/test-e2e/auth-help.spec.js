const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-AUTH-HELP';
void reqId;

const expectedAccounts = [
  ['student01', '学生'],
  ['supervisor01', '导师'],
  ['college_admin01', '学院管理人员'],
  ['school_admin01', '学校管理人员'],
];

test.describe('FEAT-AUTH-HELP local login help', () => {
  test('FEAT-AUTH-HELP:SCENARIO:001 shows the demo account help on the login page', async ({ page }) => {
    await page.goto('/auth');

    await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
    const helpPanel = page.getByLabel('演示账号与登录帮助');
    await expect(helpPanel).toBeVisible();
    await expect(helpPanel).toHaveAttribute('open', '');
    await expect(helpPanel.getByText(/默认演示密码为\s*ArcDemo123!/)).toBeVisible();
    await expect(helpPanel.getByText(/未接入 jAccount、短信验证码或扫码登录/)).toBeVisible();

    const roster = page.getByLabel('四类演示账号');
    for (const [username, role] of expectedAccounts) {
      await expect(roster.getByRole('heading', { name: username })).toBeVisible();
      await expect(roster.getByText(role)).toBeVisible();
    }

    await expect(page.getByText('短信验证码登录不属于本版本实现范围')).toBeVisible();
    await expect(page.getByRole('heading', { name: '统一身份认证' })).toBeVisible();
  });
});
