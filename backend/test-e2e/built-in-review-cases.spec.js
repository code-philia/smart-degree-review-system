const { test, expect } = require('@playwright/test');

const demoPassword = 'ArcDemo123!';

async function loginAsStudent(page) {
  await page.goto('/auth');
  await page.getByRole('textbox', { name: '账号', exact: true }).fill('student01');
  await page.getByLabel('密码', { exact: true }).fill(demoPassword);
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '欢迎回来，student01' })).toBeVisible();
}

test.describe('FEAT-BUILT-IN-REVIEW-CASES', () => {
  test('opens the fixed case and switches the PDF highlight from claim to evidence', async ({ page }) => {
    await loginAsStudent(page);
    await page.goto('/review-cases');

    await expect(page.getByRole('heading', { name: '内置审查案例' })).toBeVisible();
    await expect(page.getByText('跨页数值论点与实验论据不一致')).toBeVisible();
    await page.getByRole('link', { name: '查看案例' }).click();

    await expect(page.getByText(/研究内容段落明确声称 Z-Solver/)).toBeVisible();
    await expect(page.getByRole('button', { name: '论点（第 22 页）', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '论据（第 57 页）', exact: true })).toBeVisible();
    await expect(page.getByTestId('paper-lint-overlay-page-22')).toBeVisible({ timeout: 20_000 });

    await page.getByRole('button', { name: '论据（第 57 页）', exact: true }).click();
    const evidenceHighlight = page.getByTestId(
      'paper-lint-highlight-f_claim_evidence_inconsistency_check_1-f_claim_evidence_inconsistency_check_1_evidence_1',
    );
    await expect(evidenceHighlight).toBeVisible({ timeout: 20_000 });
    await expect(evidenceHighlight).toHaveAttribute('data-active', 'true');
  });
});
