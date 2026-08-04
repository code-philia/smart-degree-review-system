const { test, expect } = require('@playwright/test');

const REQ_ID = 'FEAT-POLISH-LOCAL';
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

async function polishVisibleText(page) {
  return page.locator('[data-testid="local-polish-result-text"]').innerText();
}

async function diffSegmentsSnapshot(page) {
  return page.locator('[data-testid="local-polish-diff-segments"]').evaluate((element) => (
    Array.from(element.querySelectorAll('[data-diff-type]')).map((segment) => ({
      type: segment.getAttribute('data-diff-type'),
      text: segment.textContent,
    }))
  ));
}

test.describe('FEAT-POLISH-LOCAL student local polish retry scenario', () => {
  test('FEAT-POLISH-LOCAL:SCENARIO:001 student retry keeps the same result and diff list for unchanged standard optimization', async ({ page }) => {
    await loginAs(page, 'student01');
    await page.goto('/local-polish');

    await expect(page.getByRole('heading', { name: /局部.*润色|局部文本润色/ })).toBeVisible();
    const input = page.getByLabel(/原始文本输入|原文|待润色文本/);
    await input.fill('这段文字存在重复重复表述！！  需要标准优化。');
    await page.getByRole('button', { name: /AI 提质|标准优化/ }).click();
    await page.getByRole('button', { name: /智能润色|开始润色|处理/ }).click();

    await expect(page.getByText(/润色完成|处理完成/)).toBeVisible();
    await expect(page.locator('[data-testid="local-polish-result-text"]')).not.toHaveText('');
    await expect(page.locator('[data-testid="local-polish-diff-segments"] [data-diff-type]').first()).toBeVisible();

    const firstResultId = await page.locator('[data-testid="local-polish-result-id"]').textContent();
    expect(firstResultId).toMatch(/\S+/);
    const firstText = await polishVisibleText(page);
    const firstDiffSegments = await diffSegmentsSnapshot(page);
    expect(firstDiffSegments.length).toBeGreaterThan(0);

    await page.getByRole('button', { name: /重新润色|重试/ }).click();
    await expect(page.locator('[data-testid="local-polish-result-id"]')).not.toHaveText(firstResultId || '');
    await expect(page.locator('[data-testid="local-polish-result-text"]')).toHaveText(firstText);

    const retryResultId = await page.locator('[data-testid="local-polish-result-id"]').textContent();
    expect(retryResultId).toMatch(/\S+/);
    expect(retryResultId).not.toBe(firstResultId);
    await expect.poll(() => diffSegmentsSnapshot(page)).toEqual(firstDiffSegments);

    const detailResponse = await page.request.get(`/api/normative/local-polish-results/${retryResultId}`);
    expect(detailResponse.status()).toBe(200);
    const detail = await detailResponse.json();
    expect(detail).toMatchObject({
      user_id: 'student01',
      original_text: '这段文字存在重复重复表述！！  需要标准优化。',
      level: 'standard',
      polished_text: firstText,
      retry_of: firstResultId,
    });
    expect(detail.diff_segments.map((segment) => ({ type: segment.type, text: segment.text }))).toEqual(firstDiffSegments);
  });
});
