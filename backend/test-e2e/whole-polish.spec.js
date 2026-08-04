const { readFile } = require('node:fs/promises');
const { test, expect } = require('@playwright/test');

const REQ_ID = 'FEAT-POLISH-WHOLE';
void REQ_ID;

const demoPassword = 'ArcDemo123!';

async function loginAs(page, username) {
  await page.goto('/auth');
  await expect(page.getByRole('heading', { name: '登录本地账号' })).toBeVisible();
  await page.getByLabel('账号').fill(username);
  await page.getByLabel('密码').fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByText(new RegExp(`已登录：${username}`))).toBeVisible();
}

async function publishPhraseMapping(page) {
  const response = await page.request.put('/api/normative/rule-configs', {
    data: {
      scope: { level: 'school' },
      rule: {
        rule_id: 'WHOLE-POLISH-PHRASE-MAP',
        title: '全文润色短语映射',
        category: '全文润色',
        severity: 'medium',
        enabled: true,
        match_params: {
          replacements: [{ original: '低效表达', replacement: '高效表达' }],
        },
        prompt: '应用管理员维护的原短语到替换短语映射',
      },
    },
  });
  expect(response.status()).toBe(200);
}

test.describe('FEAT-POLISH-WHOLE student whole-text polish scenario', () => {
  test('FEAT-POLISH-WHOLE:SCENARIO:001 student creates a traceable standard polishing result and downloads UTF-8 text', async ({ page }) => {
    await loginAs(page, 'school_admin01');
    await publishPhraseMapping(page);

    await loginAs(page, 'student01');
    await page.goto('/whole-polish');

    await expect(page.getByRole('heading', { name: /全文.*润色|全文规则润色/ })).toBeVisible();
    await page.getByLabel(/粘贴文本|待润色文本|论文文本/).fill('这里包含重复重复词！！  同时包含低效表达。');
    await page.getByRole('button', { name: /标准优化/ }).click();
    await page.getByRole('button', { name: /智能润色|开始润色|执行润色/ }).click();

    await expect(page.getByText(/润色完成|处理完成/)).toBeVisible();
    await expect(page.getByText(/标准优化/)).toBeVisible();
    await expect(page.getByText(/变更列表|修订列表|变更明细/)).toBeVisible();
    await expect(page.getByText('这里包含重复词！ 同时包含高效表达。')).toBeVisible();

    const changeList = page.getByRole('list', { name: /变更列表|修订列表|变更明细/ });
    await expect(changeList).toContainText('重复重复');
    await expect(changeList).toContainText('重复');
    await expect(changeList).toContainText('！！');
    await expect(changeList).toContainText('！');
    await expect(changeList).toContainText('低效表达');
    await expect(changeList).toContainText('高效表达');
    await expect(changeList).toContainText(/位置/);
    await expect(changeList).toContainText(/规则/);

    const resultId = await page.locator('[data-testid="whole-polish-result-id"]').textContent();
    expect(resultId).toMatch(/\S+/);
    const detailResponse = await page.request.get(`/api/normative/whole-polish-results/${resultId}`);
    expect(detailResponse.status()).toBe(200);
    const detail = await detailResponse.json();
    expect(detail).toMatchObject({
      user_id: 'student01',
      level: 'standard',
      original_text: '这里包含重复重复词！！  同时包含低效表达。',
      polished_text: '这里包含重复词！ 同时包含高效表达。',
    });
    expect(detail.changes).toEqual(expect.arrayContaining([
      expect.objectContaining({ original_text: '重复重复', new_text: '重复', position: expect.any(Number), rule: expect.any(String) }),
      expect.objectContaining({ original_text: '！！', new_text: '！', position: expect.any(Number), rule: expect.any(String) }),
      expect.objectContaining({ original_text: '低效表达', new_text: '高效表达', position: expect.any(Number), rule: expect.any(String) }),
    ]));

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /下载 UTF-8|下载结果|下载 TXT/ }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`whole-polish-${resultId}.txt`);
    const downloadPath = await download.path();
    if (!downloadPath) {
      throw new Error('Downloaded whole-polish text file path was not available');
    }
    await expect(readFile(downloadPath, 'utf8')).resolves.toBe('这里包含重复词！ 同时包含高效表达。');
  });
});
