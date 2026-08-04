import { expect, test } from '@playwright/test';

const REQ_ID = 'FEAT-NORMATIVE-DETECT';
void REQ_ID;

const studentText = [
  '摘要',
  '关键词：规范检测；规则快照',
  '引言',
  `这里包含未配对（括号。。${'问题'.repeat(70)}。`,
  '结论',
  '参考文献',
  '[1] 示例文献',
].join('\n');

async function loginAsStudent(page) {
  await page.goto('/auth');
  await page.getByLabel('账号').fill('student01');
  await page.getByLabel('密码').fill('ArcDemo123!');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
}

test.describe('FEAT-NORMATIVE-DETECT student detection scenarios', () => {
  test('FEAT-NORMATIVE-DETECT:SCENARIO:001 completes pasted-text detection and shows saved task result data', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/normative-check');

    await expect(page.getByRole('heading', { name: /规范检测|文档上传/ })).toBeVisible();
    await page.getByLabel(/论文文本|待检测文本|粘贴文本/).fill(studentText);
    await page.getByRole('button', { name: /发起检测|开始检测|上传/ }).click();

    await expect(page.getByText(/已完成|检测完成/)).toBeVisible();
    await expect(page.getByText(/100%/)).toBeVisible();
    await expect(page.getByText(/规则快照/)).toBeVisible();
    await expect(page.getByText(/问题列表|检测问题/)).toBeVisible();
    await expect(page.getByRole('table')).toContainText(/行/);
    await expect(page.getByRole('table')).toContainText(/列/);
    await expect(page.getByRole('table')).toContainText(/标点|文本质量|重复/);
    await expect(page.getByText(/创建时间|提交时间/)).toBeVisible();
  });

  test('FEAT-NORMATIVE-DETECT:SCENARIO:002 rejects oversized or non UTF-8 files without creating a task', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/normative-check');

    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toBeAttached();

    await fileInput.setInputFiles({
      name: 'oversized.txt',
      mimeType: 'text/plain',
      buffer: Buffer.alloc(5 * 1024 * 1024 + 1, 'a'),
    });
    await expect(page.getByText(/5 MB|超过|过大/)).toBeVisible();
    await expect(page.getByText(/已完成|检测完成/)).toHaveCount(0);

    await fileInput.setInputFiles({
      name: 'not-utf8.md',
      mimeType: 'text/markdown',
      buffer: Buffer.from([0xff, 0xfe, 0xfd, 0x00]),
    });
    await expect(page.getByText(/UTF-8|解码|编码/)).toBeVisible();
    await expect(page.getByText(/已完成|检测完成/)).toHaveCount(0);
  });
});
