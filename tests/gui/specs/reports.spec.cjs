const fs = require('node:fs');
const path = require('node:path');
const { test, expect, open, assertLayout, checkA11y, PDF_FIXTURE } = require('../support.cjs');
test.use({ role: 'student' });
const url = facts => '/reports/pdf/' + encodeURIComponent(facts.studentReport.id);
const pdfUrl = facts => '/api/normative/paper-lint/reports/' + facts.studentReport.id + '/pdf';
async function report(page, facts, { fixturePdf = false, status } = {}) {
  if (fixturePdf) await page.route('**' + pdfUrl(facts), r => r.fulfill({ status: 200, contentType: 'application/pdf', body: fs.readFileSync(PDF_FIXTURE) }));
  if (status) await page.route('**' + pdfUrl(facts), r => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ message: '测试 PDF 暂不可用' }) }));
  if (status || fixturePdf) test.info().annotations.push({ type: 'network-boundary', description: 'Report JSON is live; only the PDF subresource is intercepted in this case. The dedicated real-PDF test verifies actual bytes.' });
  await open(page, url(facts));
  await expect(page.getByRole('heading', { name: facts.studentReport.source_filename, exact: true })).toBeVisible();
}
test('[live-read] real saved PDF, native pages, highlights, zoom and finding navigation', async ({ page, facts }, info) => {
  test.setTimeout(150_000);
  await report(page, facts);
  const viewer = page.locator('[data-pdf-status]');
  await expect(viewer).toHaveAttribute('data-pdf-status', 'ready', { timeout: 100_000 });
  await page.getByRole('button', { name: '展开阅读工具', exact: true }).click();
  const input = page.getByRole('textbox', { name: 'PDF 页码', exact: true });
  const count = Number(await page.getByTitle('PDF 总页数', { exact: true }).innerText());
  expect(count).toBeGreaterThan(0);
  await test.step('physical page navigation and invalid-page validation', async () => {
    if (count > 1) { await input.fill('2'); await input.press('Enter'); await expect(input).toHaveValue('2'); }
    for (const value of ['0', '-1', '1.5', 'abc', String(count + 1)]) {
      await input.fill(value); await input.press('Enter');
      await expect(input).toHaveAttribute('aria-invalid', 'true');
      await expect(viewer.getByRole('alert')).toBeVisible();
    }
    await input.fill('1'); await input.press('Enter'); await expect(input).not.toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByRole('button', { name: 'PDF 上一页', exact: true })).toBeDisabled();
  });
  await test.step('highlight controls, zoom and original-PDF link', async () => {
    for (const label of ['隐藏高亮', '聚焦高亮', '显示全部高亮']) {
      await page.getByRole('button', { name: label, exact: true }).click();
      await expect(page.getByRole('button', { name: label, exact: true })).toHaveAttribute('aria-pressed', 'true');
    }
    await page.getByRole('button', { name: '放大 PDF', exact: true }).click();
    await page.getByRole('button', { name: '缩小 PDF', exact: true }).click();
    await expect(page.getByRole('link', { name: '在浏览器打开完整 PDF', exact: true })).toHaveAttribute('href', /\/pdf#page=1$/);
  });
  await test.step('a finding selects its saved physical PDF location', async () => {
    const location = finding => finding.location || finding.anchors?.[0]?.location;
    const run = facts.studentDetail.result.rule_runs.find(r => r.findings?.some(f => Number.isInteger(location(f)?.page_number)));
    const finding = run?.findings.find(f => Number.isInteger(location(f)?.page_number));
    if (!finding) { info.annotations.push({ type: 'coverage-limit', description: 'Selected saved report has no numeric page location; page controls were verified' }); return; }
    const card = page.locator('article[data-finding-key]').filter({ hasText: finding.message }).first();
    // Click the finding prose, avoiding the nested feedback/handled buttons at the card center.
    await card.locator('p').filter({ hasText: finding.message }).first().click();
    await expect(input).toHaveValue(String(location(finding).page_number));
  });
  await assertLayout(page);
  await page.screenshot({ path: info.outputPath('real-pdf.png'), fullPage: true });
});
test('[injected] live report severities and check filters remain consistent while its PDF is unavailable', async ({ page, facts }) => {
  await report(page, facts, { status: 410 });
  await expect(page.getByRole('heading', { name: '检测结果', exact: true })).toBeVisible();
  for (const pattern of [/^全部$/, /^严重 \d+$/, /^警告 \d+$/, /^提示 \d+$/, /^检测异常提醒 \d+$/]) {
    const control = page.getByRole('button', { name: pattern });
    await expect(control).toBeVisible(); await control.click(); await expect(control).toHaveAttribute('aria-pressed', 'true');
  }
  await page.getByRole('button', { name: '全部', exact: true }).click();
  await expect(page.getByRole('combobox', { name: '按检查项筛选', exact: true })).toBeVisible();
});
for (const status of [403, 404, 500]) test(`[injected] saved-report ${status} is a visible error, not an empty successful result`, async ({ page, facts }) => {
  await page.route('**/api/normative/paper-lint/reports/' + facts.studentReport.id, r => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify({ message: '测试：无法读取报告' }) }));
  await open(page, url(facts));
  await expect(page.getByRole('alert').getByText('报告暂不可用', { exact: true })).toBeVisible();
  await expect(page.locator('[data-finding-key]')).toHaveCount(0);
});
for (const status of [403, 404, 410]) test(`[injected] PDF ${status} preserves readable report findings and offers recovery`, async ({ page, facts }) => {
  await report(page, facts, { status });
  await expect(page.getByRole('heading', { name: '检测结果', exact: true })).toBeVisible();
  await expect(page.locator('[data-pdf-status]')).toHaveAttribute('data-pdf-status', 'error');
  await expect(page.locator('[data-pdf-status]').getByRole('alert')).toBeVisible();
});
test('[injected] unavailable document metrics do not hide the saved report', async ({ page, facts }) => {
  await page.route('**/document-metrics', r => r.fulfill({ status: 503, contentType: 'application/json', body: '{}' }));
  await report(page, facts, { status: 410 });
  await expect(page.getByRole('heading', { name: facts.studentReport.source_filename, exact: true })).toBeVisible();
  await expect(page.getByText('未统计', { exact: true }).first()).toBeVisible();
});
test('[injected] live Chinese JSON, Markdown, Text and Docx downloads work while the PDF is unavailable', async ({ page, facts }, info) => {
  await report(page, facts, { status: 410 });
  for (const [name, extension] of [['Json', '.json'], ['Markdown', '.md'], ['文本', '.txt'], ['Docx', '.docx']]) {
    await page.getByRole('button', { name: '下载检测报告', exact: true }).click();
    const pending = page.waitForEvent('download', { timeout: 35_000 });
    await page.getByRole('button', { name: '导出 ' + name, exact: true }).click();
    const download = await pending;
    expect(download.suggestedFilename().toLowerCase()).toContain(extension);
    const saved = info.outputPath(download.suggestedFilename()); await download.saveAs(saved);
    expect(fs.statSync(saved).size).toBeGreaterThan(30);
    if (name === 'Json') expect(JSON.parse(fs.readFileSync(saved, 'utf8'))).toBeTruthy();
    await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  }
});
test('[injected] live report dark appearance and accessibility retain findings while the PDF is unavailable', async ({ page, facts }, info) => {
  await page.addInitScript(() => localStorage.setItem('sjtu-ui-theme', 'dark'));
  await report(page, facts, { status: 410 });
  await expect(page.locator('html')).toHaveClass(/dark/);
  await checkA11y(page, info);
});
