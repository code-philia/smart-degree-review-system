const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-NORMATIVE-FORMAT-RULES';
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

test.describe('FEAT-NORMATIVE-FORMAT-RULES default normative check scenario', () => {
  test('FEAT-NORMATIVE-FORMAT-RULES:SCENARIO:001 detects pairing, repeated punctuation, and long sentence issues with line and column fields', async ({ page }) => {
    await loginAsStudent(page);

    await page.goto('/normative-check');
    await expect(page.getByRole('heading', { name: '默认规范检测规则' })).toBeVisible();
    await expect(page.getByText(/当前登录用户：student01（STUDENT）/)).toBeVisible();

    const scenarioText = [
      '摘要',
      '关键词',
      '引言',
      `学生文本包含未配对（括号。。${'内容'.repeat(70)}。`,
      '结论',
      '参考文献',
      '[1] 示例文献',
    ].join('\n');

    await page.getByLabel('待检测文本').fill(scenarioText);
    await page.getByRole('button', { name: '运行默认规则' }).click();

    await expect(page.getByText(/已返回 \d+ 条问题。/)).toBeVisible();
    const table = page.getByRole('table');

    await expect(table.getByText('NORM-002')).toBeVisible();
    await expect(table.getByText('NORM-003')).toBeVisible();
    await expect(table.getByText('NORM-006')).toBeVisible();
    await expect(table.getByText('标点配对')).toBeVisible();
    await expect(table.getByText('重复标点')).toBeVisible();
    await expect(table.getByText('文本质量')).toBeVisible();
    await expect(table.getByText('行号')).toBeVisible();
    await expect(table.getByText('列号')).toBeVisible();
  });

  test('FEAT-NORMATIVE-FORMAT-RULES:SCENARIO:002 shows login-required state for anonymous users on the page route', async ({ page }) => {
    await page.goto('/normative-check');

    await expect(page.getByRole('heading', { name: '默认规范检测' })).toBeVisible();
    await expect(page.getByText(/请先登录后运行/)).toBeVisible();
    await expect(page.getByRole('link', { name: '前往登录' })).toHaveAttribute('href', '/auth');
  });
});
