const fs = require('node:fs');
const { test, expect, open, readyTable, LIVE_PDF, PDF_FIXTURE, run, record, state, BASE, installGuard } = require('../support.cjs');
test.use({ role: 'student', allowWrites: true });
test.describe.configure({ mode: 'default' });

test('[live-write] marked PDF review, saved report, feedback, all exports, admin visibility and exact batch deletion', async ({ page, browser, facts }, info) => {
  test.skip(process.env.GUI_ALLOW_LIVE_WRITES !== '1' || process.env.GUI_ALLOW_EMAIL !== '1', 'Explicit live-data and completion-email approval flags are required');
  if (!LIVE_PDF || !fs.existsSync(LIVE_PDF)) throw new Error('GUI_LIVE_PDF must point to an approved real research PDF for the live lifecycle');
  test.setTimeout(360_000);
  const prefix = run().prefix, names = [prefix + '-A.pdf', prefix + '-B.pdf'], reports = [];
  const startingCredit = (await (await page.request.get('/api/normative/paper-lint/credit')).json()).available_cny;
  for (const filename of names) await test.step('actual free-rule review: ' + filename, async () => {
    await open(page, '/paper-upload');
    await page.getByRole('button', { name: '展开选择', exact: true }).click();
    await page.getByRole('button', { name: '清空全部检测规则', exact: true }).click();
    await page.getByRole('checkbox', { name: /^核心章节完整性/ }).check();
    await page.getByRole('checkbox', { name: /^关键词数量/ }).check();
    await page.getByLabel('上传待审查 PDF', { exact: true }).setInputFiles({ name: filename, mimeType: 'application/pdf', buffer: fs.readFileSync(LIVE_PDF) });
    const pending = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/normative/paper-lint/run', { timeout: 35_000 });
    await page.getByRole('button', { name: '开始检测', exact: true }).click();
    const accepted = await pending;
    expect(accepted.ok(), 'Actual report submission should be accepted').toBeTruthy();
    const job = await accepted.json();
    if (job.job_id) record({ kind: 'job', id: job.job_id, filename });
    await page.waitForURL(/\/reports\/pdf\/[^/?]+/, { timeout: 140_000 });
    const id = new URL(page.url()).pathname.split('/').pop();
    record({ kind: 'report', id, filename, job_id: job.job_id || null });
    reports.push({ id, filename });
    await expect(page.getByRole('heading', { name: filename, exact: true })).toBeVisible();
    const saved = await page.request.get('/api/normative/paper-lint/reports/' + id);
    expect(saved.ok()).toBeTruthy();
    expect((await saved.json()).source_filename).toBe(filename);
  });

  await test.step('a new finding vote and reason are saved on this run’s own report', async () => {
    await open(page, '/reports/pdf/' + reports[0].id);
    await expect(page.getByRole('heading', { name: names[0], exact: true })).toBeVisible();
    const card = page.locator('[data-finding-key]').filter({ has: page.getByRole('button', { name: '需要改进', exact: true }) }).first();
    await expect(card).toBeVisible();
    const vote = page.waitForResponse(r => r.request().method() === 'PUT' && /\/feedback$/.test(new URL(r.url()).pathname));
    await card.getByRole('button', { name: '需要改进', exact: true }).click();
    const voteResponse = await vote;
    expect(voteResponse.ok(), `Finding feedback HTTP ${voteResponse.status()}: ${await voteResponse.text()}`).toBeTruthy();
    await card.getByLabel('负面反馈原因', { exact: true }).selectOption('false_positive');
    await card.getByLabel('反馈补充说明', { exact: true }).fill(prefix + ' 自动化 GUI 测试原因，仅用于本次测试');
    const reason = page.waitForResponse(r => r.request().method() === 'PUT' && /\/feedback$/.test(new URL(r.url()).pathname));
    await card.getByRole('button', { name: '提交反馈', exact: true }).click();
    expect((await reason).ok()).toBeTruthy();
    const success = page.getByRole('dialog', { name: '提交成功', exact: true });
    await expect(success).toBeVisible();
    await success.getByRole('button', { name: '知道了', exact: true }).click();
  });

  await test.step('actual system feedback appears in the administrator console', async () => {
    await page.getByRole('button', { name: '使用反馈', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '使用反馈', exact: true });
    await dialog.getByRole('radio', { name: '4 星', exact: true }).focus();
    await dialog.getByRole('radio', { name: '4 星', exact: true }).press('Space');
    await dialog.getByLabel('补充意见（可选）', { exact: true }).fill(prefix + ' 本次 Playwright 自动化测试反馈，测试完成后清理');
    const pending = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/normative/feedback/system-feedback');
    await dialog.getByRole('button', { name: '提交反馈', exact: true }).click();
    const response = await pending; expect(response.ok()).toBeTruthy();
    const saved = await response.json(); expect(saved.id).toBeTruthy();
    record({ kind: 'system-feedback', id: saved.id, comment: prefix + ' 本次 Playwright 自动化测试反馈，测试完成后清理' });
    await expect(dialog.getByText('感谢反馈！', { exact: true })).toBeVisible();
    await dialog.getByRole('button', { name: '完成', exact: true }).click();
    const adminContext = await browser.newContext({ baseURL: BASE, storageState: state('admin'), locale: 'zh-CN', viewport: { width: 1440, height: 1000 } });
    await installGuard(adminContext);
    const admin = await adminContext.newPage();
    try {
      await open(admin, '/admin/reports'); await readyTable(admin, '全部用户检测报告');
      await admin.getByRole('searchbox', { name: '搜索报告', exact: true }).fill(prefix);
      await expect(admin.getByRole('table', { name: '全部用户检测报告' }).locator('tbody tr')).toHaveCount(2);
      for (const filename of names) await expect(admin.getByRole('table', { name: '全部用户检测报告' })).toContainText(filename);
      await admin.getByRole('link', { name: '反馈监管', exact: true }).click();
      await readyTable(admin, '全部用户反馈');
      await admin.getByRole('searchbox', { name: '搜索反馈', exact: true }).fill(prefix);
      await expect(admin.getByRole('table', { name: '全部用户反馈' })).toContainText('自动化测试反馈');
      await admin.screenshot({ path: info.outputPath('new-feedback-visible-to-admin.png'), fullPage: true });
    } finally { await adminContext.close(); }
  });

  const exportFailures = [];
  await test.step('all six export formats produce actual downloaded files', async () => {
    for (const [label, extension] of [['PDF', '.pdf'], ['Markdown', '.md'], ['文本', '.txt'], ['Docx', '.docx'], ['图片', '.zip'], ['Json', '.json']]) {
      try {
        await page.getByRole('button', { name: '下载检测报告', exact: true }).click();
        const pending = page.waitForEvent('download', { timeout: 45_000 });
        await page.getByRole('button', { name: '导出 ' + label, exact: true }).click();
        const download = await pending;
        expect(download.suggestedFilename().toLowerCase()).toContain(extension);
        const saved = info.outputPath(download.suggestedFilename()); await download.saveAs(saved);
        expect(fs.statSync(saved).size).toBeGreaterThan(30);
        if (label === 'PDF') expect(fs.readFileSync(saved).subarray(0, 4).toString()).toBe('%PDF');
        if (label === 'Json') expect(JSON.parse(fs.readFileSync(saved, 'utf8'))).toBeTruthy();
      } catch (error) { exportFailures.push({ format: label, message: error.message.slice(0, 900) }); }
      const cancel = page.getByRole('button', { name: '取消导出', exact: true });
      if (await cancel.isVisible()) await cancel.click();
      await page.keyboard.press('Escape');
      await expect(page.getByRole('dialog')).toHaveCount(0);
    }
    await info.attach('actual-export-results.json', { body: Buffer.from(JSON.stringify(exportFailures)), contentType: 'application/json' });
    expect.soft(exportFailures).toEqual([]);
  });

  await test.step('actual selected-report ZIP contains only this run’s two marked reports', async () => {
    await open(page, '/reports');
    await page.getByRole('searchbox', { name: '搜索检测报告', exact: true }).fill(prefix);
    const table = page.getByRole('table', { name: '规范性检测报告', exact: true });
    await expect(table.locator('tbody tr')).toHaveCount(2);
    await page.getByRole('button', { name: '批量管理', exact: true }).click();
    for (const filename of names) await page.getByLabel('选择报告：' + filename, { exact: true }).check();
    await page.getByRole('button', { name: '导出选中（2）', exact: true }).click();
    const pending = page.waitForEvent('download', { timeout: 45_000 });
    await page.getByRole('dialog', { name: '批量导出报告', exact: true }).getByRole('button', { name: '导出 Json', exact: true }).click();
    const download = await pending; expect(download.suggestedFilename()).toMatch(/\.zip$/);
    const file = info.outputPath(download.suggestedFilename()); await download.saveAs(file);
    const { unzipSync, strFromU8 } = require('fflate');
    const entries = unzipSync(new Uint8Array(fs.readFileSync(file)));
    const jsonEntries = Object.entries(entries).filter(([name]) => name.endsWith('.json'));
    expect(jsonEntries).toHaveLength(2);
    for (const [, bytes] of jsonEntries) expect(strFromU8(bytes)).toContain(prefix);
    await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
  });

  await test.step('delete exactly the registered new reports and preserve earlier history', async () => {
    await page.getByRole('button', { name: '删除选中（2）', exact: true }).click();
    const dialog = page.getByRole('alertdialog', { name: '删除选中的报告？', exact: true });
    await expect(dialog).toContainText('已选择 2 份报告');
    const pending = page.waitForResponse(r => r.request().method() === 'DELETE' && new URL(r.url()).pathname === '/api/normative/paper-lint/reports');
    await dialog.getByRole('button', { name: '确认删除', exact: true }).click();
    const response = await pending; expect(response.ok()).toBeTruthy();
    expect(new Set((await response.json()).deleted_ids)).toEqual(new Set(reports.map(r => r.id)));
    for (const report of reports) expect((await page.request.get('/api/normative/paper-lint/reports/' + report.id)).status()).toBe(404);
    const remaining = (await (await page.request.get('/api/normative/paper-lint/reports')).json()).records;
    for (const before of facts.studentReports.records) expect(remaining.some(r => r.id === before.id)).toBeTruthy();
  });
  const finalCredit = (await (await page.request.get('/api/normative/paper-lint/credit')).json()).available_cny;
  expect(finalCredit, 'These two deterministic-rule reviews must not consume model credit').toBe(startingCredit);
});

test('[live-write] a rejected non-paper remains readable and its visible finding feedback works', async ({ page }, info) => {
  test.skip(process.env.GUI_ALLOW_LIVE_WRITES !== '1' || process.env.GUI_ALLOW_EMAIL !== '1', 'Live-data and email approval flags are required');
  test.setTimeout(100_000);
  const filename = run().prefix + '-non-paper.pdf';
  await open(page, '/paper-upload');
  await page.getByRole('button', { name: '展开选择', exact: true }).click();
  await page.getByRole('button', { name: '清空全部检测规则', exact: true }).click();
  await page.getByRole('checkbox', { name: /^核心章节完整性/ }).check();
  await page.getByLabel('上传待审查 PDF', { exact: true }).setInputFiles({ name: filename, mimeType: 'application/pdf', buffer: fs.readFileSync(PDF_FIXTURE) });
  const accepted = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/normative/paper-lint/run');
  await page.getByRole('button', { name: '开始检测', exact: true }).click();
  const submitted = await accepted; expect(submitted.ok()).toBeTruthy();
  const job = await submitted.json(); if (job.job_id) record({ kind: 'job', id: job.job_id, filename });
  await page.waitForURL(/\/reports\/pdf\/[^/?]+/, { timeout: 60_000 });
  const id = new URL(page.url()).pathname.split('/').pop(); record({ kind: 'report', id, filename });
  await expect(page.getByRole('heading', { name: '论文编译校验', exact: true })).toBeVisible();
  const card = page.locator('[data-finding-key]').filter({ hasText: '所有论文规则均未检测' }).first();
  await expect(card).toBeVisible();
  const pending = page.waitForResponse(r => r.request().method() === 'PUT' && /\/feedback$/.test(new URL(r.url()).pathname));
  await card.getByRole('button', { name: '需要改进', exact: true }).click();
  const response = await pending, body = await response.text();
  await info.attach('actual-admission-feedback.json', { body: Buffer.from(JSON.stringify({ status: response.status(), body })), contentType: 'application/json' });
  expect(response.ok(), 'A feedback button displayed to the user must accept feedback: HTTP ' + response.status() + ' ' + body).toBeTruthy();
});
