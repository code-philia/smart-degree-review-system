const { readFile } = require('node:fs/promises');
const { test, expect } = require('@playwright/test');

const REQ_ID = 'FEAT-POLISH-HISTORY';
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

async function createWholePolishResult(page, sourceFilename, suffix) {
  const response = await page.request.post('/api/normative/whole-polish-results', {
    data: {
      text: `全文润色历史 ${suffix} 存在重复重复表达！！`,
      level: 'standard',
      source_type: 'file',
      source_filename: sourceFilename,
    },
  });
  expect(response.status()).toBe(201);
  const result = await response.json();
  expect(result.user_id).toBeTruthy();
  expect(result.source_filename).toBe(sourceFilename);
  expect(result.polished_text).not.toBe(result.original_text);
  return result;
}

async function createLocalPolishResult(page, suffix) {
  const response = await page.request.post('/api/normative/local-polish-results', {
    data: {
      text: `局部润色历史 ${suffix} 包含重复重复表达！！`,
      level: 'enhanced',
    },
  });
  expect(response.status()).toBe(201);
  const result = await response.json();
  expect(result.user_id).toBeTruthy();
  expect(result.polished_text).not.toBe(result.original_text);
  return result;
}

test.describe('FEAT-POLISH-HISTORY student history scenario', () => {
  test('FEAT-POLISH-HISTORY:SCENARIO:001 student01 sees only own whole and local polish records and can inspect/download the result', async ({ page }) => {
    await loginAs(page, 'supervisor01');
    const hiddenSupervisorRecord = await createWholePolishResult(page, `supervisor-hidden-polish-${Date.now()}.txt`, '导师不可见记录');

    await loginAs(page, 'student01');
    const olderWhole = await createWholePolishResult(page, `student01-whole-history-${Date.now()}.txt`, '全文记录');
    const newerLocal = await createLocalPolishResult(page, '局部记录');

    await page.goto('/polish-history');
    await expect(page.getByRole('heading', { name: '润色记录' })).toBeVisible();
    await expect(page.getByText(/共 \d+ 条记录/)).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '序号' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '文档名称' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '润色模式' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '润色等级' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '报告生成时间' })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: '操作' })).toBeVisible();

    const rows = page.getByRole('row');
    const wholeRow = rows.filter({ hasText: olderWhole.source_filename });
    const localRow = rows.filter({ hasText: '局部润色' }).filter({ hasText: 'AI 重构' });
    await expect(wholeRow).toBeVisible();
    await expect(localRow).toBeVisible();
    await expect(page.getByText(/supervisor-hidden-polish-/)).toHaveCount(0);
    await expect(wholeRow).toContainText('全文润色');
    await expect(wholeRow).toContainText('AI 提质');
    await expect(localRow).toContainText('局部润色');
    await expect(localRow).toContainText('AI 重构');

    const localBox = await localRow.boundingBox();
    const wholeBox = await wholeRow.boundingBox();
    expect(localBox).not.toBeNull();
    expect(wholeBox).not.toBeNull();
    expect(localBox.y).toBeLessThan(wholeBox.y);

    await localRow.getByRole('link', { name: '查看差异' }).click();
    await expect(page).toHaveURL(new RegExp(`/polish-history/local/${newerLocal.id}$`));
    await expect(page.getByRole('heading', { name: '差异查看' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '原文' })).toBeVisible();
    await expect(page.getByRole('heading', { name: '润色结果' })).toBeVisible();
    await expect(page.getByText(newerLocal.original_text)).toBeVisible();
    await expect(page.getByText(newerLocal.polished_text)).toBeVisible();

    const detailResponse = await page.request.get(`/api/normative/polish-history/local/${newerLocal.id}`);
    expect(detailResponse.status()).toBe(200);
    const detail = await detailResponse.json();
    expect(detail).toMatchObject({
      id: newerLocal.id,
      user_id: 'student01',
      polish_type: 'local',
      original_text: newerLocal.original_text,
      polished_text: newerLocal.polished_text,
    });

    const hiddenDetailResponse = await page.request.get(`/api/normative/polish-history/whole/${hiddenSupervisorRecord.id}`);
    expect(hiddenDetailResponse.status()).toBe(404);

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载 .txt' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe(`局部润色-${newerLocal.id}.txt`);
    const downloadPath = await download.path();
    if (!downloadPath) {
      throw new Error('Downloaded polish result text file path was not available');
    }
    await expect(readFile(downloadPath, 'utf8')).resolves.toBe(newerLocal.polished_text);
  });
});
