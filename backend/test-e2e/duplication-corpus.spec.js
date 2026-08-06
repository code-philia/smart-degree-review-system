const { test, expect } = require('@playwright/test');

const reqId = 'FEAT-DUPLICATION-CORPUS';
void reqId;

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录' }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

test.describe('FEAT-DUPLICATION-CORPUS local corpus scenarios', () => {
  test('FEAT-DUPLICATION-CORPUS:SCENARIO:001 school admin imports a non-empty UTF-8 sample and it is persisted for later similarity use', async ({ page }) => {
    await loginAs(page, 'school_admin01');
    await page.goto('/duplication-corpus');

    await expect(page.getByRole('heading', { name: '本地比对样本库' })).toBeVisible();
    await expect(page.getByText(/不表示已接入真实校内论文库/)).toBeVisible();

    const uniqueTitle = `E2E 本地比对样本 ${Date.now()}`;
    const sampleText = 'school_admin01 准备的非空 UTF-8 文本，用于后续相似度检测读取。';

    await page.getByLabel('标题').fill(uniqueTitle);
    await page.getByLabel('学科').fill('计算机科学');
    await page.getByLabel('年份').fill('2024');
    await page.getByLabel('样本文本').fill(sampleText);
    await page.getByRole('button', { name: '保存样本' }).click();

    await expect(page.getByRole('heading', { name: uniqueTitle })).toBeVisible();
    await expect(page.getByText(/计算机科学 · 2024 · 粘贴文本/)).toBeVisible();

    const response = await page.request.get('/api/normative/duplication-corpus');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.samples).toEqual(expect.arrayContaining([
      expect.objectContaining({
        title: uniqueTitle,
        subject: '计算机科学',
        year: 2024,
        content: sampleText,
        source_type: 'paste',
        created_by: 'school_admin01',
      }),
    ]));
  });
});
