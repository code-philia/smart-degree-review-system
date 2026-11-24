const path = require('node:path');
const fs = require('node:fs');
const { test, expect, open, assertLayout, checkA11y, PDF_FIXTURE } = require('../support.cjs');
const policy = require('../../../shared/paper-lint-credit-policy.json');

test.use({ role: 'student' });

const HISTORY_RULE_IDS = new Set([
  'abstract_numeric_consistency_check', 'sjtu_rule_18', 'sjtu_rule_22', 'sjtu_rule_24',
  'sjtu_rule_28', 'sjtu_rule_31', 'sjtu_rule_32', 'required_section_completeness_check',
  'chinese_english_symbol_mix_check', 'keyword_count_check', 'abstract_object_number_check',
  'chapter_new_page_check', 'bilingual_keywords_correspondence_check',
  'bilingual_abstract_consistency_check', 'typo_detection_check',
]);
const CONTENT_ORDER = [
  'typo_detection_check', 'bilingual_abstract_consistency_check',
  'bilingual_keywords_correspondence_check', 'chinese_english_symbol_mix_check', 'sjtu_rule_32',
];
const apiResponse = (page, suffix) => page.waitForResponse(response =>
  response.request().method() === 'GET' && new URL(response.url()).pathname === `/api${suffix}`);
const ruleSection = page => page.locator('section[aria-label="检测规则选择"]');
const historyTable = page => page.getByRole('table', { name: '规范性检测报告', exact: true });
const rowNames = table => table.locator('tbody a[title]').evaluateAll(links => links.map(link => link.title));
const selectedExport = (page, count) => page.getByRole('button', { name: `导出选中（${count}）`, exact: true });

test.beforeEach(async ({ page }) => {
  // Initialize only the first navigation; later reloads must test actual preference persistence.
  await page.addInitScript(() => {
    if (!sessionStorage.getItem('gui-student-preferences-initialized')) {
      localStorage.setItem('sjtu-ui-locale', 'zh');
      localStorage.setItem('sjtu-ui-theme', 'light');
      sessionStorage.setItem('gui-student-preferences-initialized', 'yes');
    }
  });
});

async function upload(page) {
  const responsePromise = apiResponse(page, '/normative/paper-lint/rules');
  await open(page, '/paper-upload');
  const response = await responsePromise;
  expect(response.ok(), 'Live rule catalog should be readable').toBeTruthy();
  const catalog = await response.json();
  await expect(page.getByRole('heading', { name: '论文上传', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '展开选择', exact: true })).toBeEnabled();
  return catalog.rules.filter(rule => rule.enabled_in_mvp);
}

async function history(page) {
  const responsePromise = apiResponse(page, '/normative/paper-lint/reports');
  await open(page, '/reports');
  const response = await responsePromise;
  expect(response.ok(), 'Live student report history should be readable').toBeTruthy();
  const { records } = await response.json();
  const reports = records.filter(report => report.selected_rule_ids.length > 0 &&
    report.selected_rule_ids.every(id => HISTORY_RULE_IDS.has(id)));
  await expect(page.getByRole('heading', { name: '历史报告', exact: true })).toBeVisible();
  if (reports.length) await expect(historyTable(page)).toBeVisible();
  else await expect(page.getByText('暂无检测记录', { exact: true })).toBeVisible();
  return reports;
}

async function expandRules(page) {
  await page.getByRole('button', { name: '展开选择', exact: true }).click();
  await expect(page.getByRole('button', { name: '收起选择', exact: true })).toHaveAttribute('aria-expanded', 'true');
}

async function settings(page) {
  await page.getByRole('button', { name: '设置', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '设置', exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function feedback(page) {
  await page.getByRole('button', { name: '使用反馈', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: '使用反馈', exact: true });
  await expect(dialog).toBeVisible();
  return dialog;
}

async function pageSize(page, size) {
  await page.getByRole('combobox', { name: '每页显示条数', exact: true }).click();
  await page.getByRole('option', { name: `${size} 条/页`, exact: true }).click();
}

test('[live-read] student navigation exposes upload/history with the correct active item', async ({ page }) => {
  await upload(page);
  // BreadcrumbPage also has role=link; these assertions concern the sidebar links.
  const navigation = page.getByLabel('主导航菜单', { exact: true });
  const uploadLink = navigation.getByRole('link', { name: '论文上传', exact: true });
  const historyLink = navigation.getByRole('link', { name: '历史报告', exact: true });
  await expect(uploadLink).toHaveAttribute('aria-current', 'page');
  await historyLink.click();
  await expect(page).toHaveURL(/\/reports(?:\?|$)/);
  await expect(historyLink).toHaveAttribute('aria-current', 'page');
  await uploadLink.click();
  await expect(page.getByRole('heading', { name: '论文上传', exact: true })).toBeVisible();
  await expect(uploadLink).toHaveAttribute('aria-current', 'page');
});

test('[live-read] a selected local PDF can be removed and selected again without uploading', async ({ page }) => {
  await upload(page);
  const input = page.getByLabel('上传待审查 PDF', { exact: true });
  const start = page.getByRole('button', { name: '开始检测', exact: true });
  const submissions = [];
  page.on('request', request => { if (request.method() === 'POST' && /\/paper-lint\/run(?:\?|$)/.test(request.url())) submissions.push(request.url()); });
  await expect(start).toBeDisabled();
  await input.setInputFiles(PDF_FIXTURE);
  await expect(page.getByText(path.basename(PDF_FIXTURE), { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '移除文件', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: '移除文件', exact: true }).click();
  await expect(page.getByText('点击或将文件拖拽至此处上传', { exact: true })).toBeVisible();
  await expect(start).toBeDisabled();
  await input.setInputFiles(PDF_FIXTURE);
  await expect(page.getByText(path.basename(PDF_FIXTURE), { exact: true })).toBeVisible();
  expect(submissions).toEqual([]);
});

test('[live-read] dropping a local PDF chooses the file without submitting it', async ({ page }) => {
  await upload(page);
  const bytes = Array.from(fs.readFileSync(PDF_FIXTURE));
  const transfer = await page.evaluateHandle(({ bytes, filename }) => {
    const data = new DataTransfer();
    data.items.add(new File([new Uint8Array(bytes)], filename, { type: 'application/pdf' }));
    return data;
  }, { bytes, filename: path.basename(PDF_FIXTURE) });
  try {
    await page.locator('[data-appearance-upload-dropzone]').dispatchEvent('drop', { dataTransfer: transfer });
    await expect(page.getByText(path.basename(PDF_FIXTURE), { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: '移除文件', exact: true })).toBeVisible();
  } finally { await transfer.dispose(); }
});

for (const sample of [
  { title: 'non-PDF', name: 'GUI_TEST_invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('test'), error: '仅支持上传 PDF 文件' },
  { title: 'empty PDF', name: 'GUI_TEST_empty.pdf', mimeType: 'application/pdf', buffer: Buffer.alloc(0), error: 'PDF 文件不能为空' },
]) {
  test(`[live-read] local ${sample.title} validation leaves detection disabled`, async ({ page }) => {
    await upload(page);
    await page.getByLabel('上传待审查 PDF', { exact: true }).setInputFiles({ name: sample.name, mimeType: sample.mimeType, buffer: sample.buffer });
    await expect(page.getByRole('alert').filter({ hasText: sample.error })).toBeVisible();
    await expect(page.getByRole('button', { name: '开始检测', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: '移除文件', exact: true })).toHaveCount(0);
  });
}

test('[live-read] local PDF larger than 50 MiB is rejected before any submission', async ({ page }) => {
  await upload(page);
  // Construct inside the isolated browser to avoid transferring a 50 MiB test payload.
  await page.getByLabel('上传待审查 PDF', { exact: true }).evaluate(input => {
    const data = new DataTransfer();
    data.items.add(new File([new ArrayBuffer(50 * 1024 * 1024 + 1)], 'GUI_TEST_too-large.pdf', { type: 'application/pdf' }));
    input.files = data.files;
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  await expect(page.getByRole('alert').filter({ hasText: 'PDF 文件大小不能超过 50 MB' })).toBeVisible();
  await expect(page.getByRole('button', { name: '开始检测', exact: true })).toBeDisabled();
});

test('[live-read] all available catalog rules are selected and a collapsed subset is retained', async ({ page }) => {
  const rules = await upload(page);
  const available = rules.filter(rule => rule.available);
  expect(available.length).toBeGreaterThan(0);
  await expect(ruleSection(page).getByRole('checkbox')).toHaveCount(0);
  await expandRules(page);
  await expect(ruleSection(page).getByRole('checkbox', { checked: true })).toHaveCount(available.length);
  const checkbox = ruleSection(page).locator('input[type="checkbox"]:enabled').first();
  await checkbox.uncheck();
  await page.getByRole('button', { name: '收起选择', exact: true }).click();
  await expect(ruleSection(page).getByRole('checkbox')).toHaveCount(0);
  await expandRules(page);
  await expect(ruleSection(page).getByRole('checkbox', { checked: true })).toHaveCount(available.length - 1);
  await expect(checkbox).not.toBeChecked();
});

test('[live-read] global clear/select-all updates rule count and selection validation', async ({ page }) => {
  const rules = await upload(page);
  await expandRules(page);
  await page.getByRole('button', { name: '清空全部检测规则', exact: true }).click();
  await expect(ruleSection(page).getByRole('checkbox', { checked: true })).toHaveCount(0);
  await expect(page.getByRole('alert').filter({ hasText: '请至少选择一项检测规则' })).toBeVisible();
  await expect(page.getByRole('button', { name: '开始检测', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '全选全部检测规则', exact: true }).click();
  await expect(ruleSection(page).getByRole('checkbox', { checked: true })).toHaveCount(rules.filter(rule => rule.available).length);
  await expect(page.getByRole('alert').filter({ hasText: '请至少选择一项检测规则' })).toHaveCount(0);
});

test('[live-read] group selection changes only the chosen rule group', async ({ page }) => {
  await upload(page);
  await expandRules(page);
  for (const group of ['格式规范', '内容规范', '论文逻辑审查']) {
    const section = page.locator(`section[aria-label="${group}检测规则"]`);
    const inputs = section.locator('input[type="checkbox"]:enabled');
    if (!await inputs.count()) continue;
    const before = await ruleSection(page).getByRole('checkbox', { checked: true }).count();
    const groupCount = await inputs.count();
    await page.getByRole('button', { name: `清空${group}`, exact: true }).click();
    await expect(section.locator('input[type="checkbox"]:checked')).toHaveCount(0);
    await expect(ruleSection(page).getByRole('checkbox', { checked: true })).toHaveCount(before - groupCount);
    await page.getByRole('button', { name: `全选${group}`, exact: true }).click();
    await expect(ruleSection(page).getByRole('checkbox', { checked: true })).toHaveCount(before);
  }
});

test('[live-read] content rule ordering and paid estimates match the published policy', async ({ page }) => {
  const rules = await upload(page);
  await expandRules(page);
  const content = page.locator('section[aria-label="内容规范检测规则"]');
  const expectedOrder = CONTENT_ORDER.filter(id => rules.some(rule => rule.rule_id === id));
  const titles = new Map(rules.map(rule => [rule.rule_id, rule.title]));
  await expect(content.locator('.credit-rule-name')).toHaveText(expectedOrder.map(id => titles.get(id)));
  await expect(page.locator('.credit-rule-price')).toHaveCount(rules.filter(rule => Object.hasOwn(policy.estimated_cny, rule.rule_id)).length);
  const total = rules.filter(rule => rule.available).reduce((sum, rule) => sum + Number(policy.estimated_cny[rule.rule_id] || 0), 0);
  await expect(page.locator('.credit-estimate strong')).toHaveText(`¥${total.toFixed(2)}`);
  await page.getByRole('button', { name: '清空全部检测规则', exact: true }).click();
  await expect(page.locator('.credit-estimate strong')).toHaveText('¥0.00');
  await page.getByRole('button', { name: '全选论文逻辑审查', exact: true }).click();
  await expect(page.locator('.credit-estimate strong')).toHaveText(`¥${Number(policy.estimated_cny.abstract_numeric_consistency_check).toFixed(2)}`);
});

test('[live-read] credit popover displays the authenticated balance and accounting details', async ({ page }) => {
  const responsePromise = apiResponse(page, '/normative/paper-lint/credit');
  await upload(page);
  const response = await responsePromise;
  expect(response.ok()).toBeTruthy();
  const credit = await response.json();
  const control = page.getByRole('button', { name: `可用额度 ${Number(credit.available_cny).toFixed(2)} 元，查看额度说明`, exact: true });
  await expect(control).toBeEnabled();
  await control.click();
  for (const [label, field] of [['账号总额度', 'granted_cny'], ['已使用', 'spent_cny']]) {
    await expect(page.getByText(label, { exact: true }).locator('..').locator('dd')).toHaveText(`¥${Number(credit[field]).toFixed(2)}`);
  }
  if (Number(credit.reserved_cny) > 0) await expect(page.getByText('预占额度', { exact: true })).toBeVisible();
  await expect(page.getByText('仅模型检测消耗额度，按实际 token 用量结算。', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByText('账号总额度', { exact: true })).toHaveCount(0);
});

test('[live-read] feedback requires a score and supports keyboard rating without sending feedback', async ({ page }) => {
  await upload(page);
  const requests = [];
  page.on('request', request => { if (request.method() === 'POST' && request.url().includes('/system-feedback')) requests.push(request.url()); });
  const dialog = await feedback(page);
  await dialog.getByRole('button', { name: '提交反馈', exact: true }).click();
  await expect(dialog.getByRole('alert')).toHaveText('请先选择满意度');
  await dialog.getByRole('radio', { name: '3 星', exact: true }).focus();
  await dialog.getByRole('radio', { name: '3 星', exact: true }).press('Space');
  await dialog.getByRole('radio', { name: '3 星', exact: true }).press('ArrowRight');
  await expect(dialog.getByRole('radio', { name: '4 星', exact: true })).toBeChecked();
  await expect(dialog.getByText('4 星 · 满意', { exact: true })).toBeVisible();
  expect(requests).toEqual([]);
});

test('[live-read] feedback multi-select and 1000-character counter stay within form limits', async ({ page }) => {
  await upload(page);
  const dialog = await feedback(page);
  await dialog.getByRole('checkbox', { name: '检测准确性', exact: true }).check();
  await dialog.getByRole('checkbox', { name: '系统响应速度', exact: true }).check();
  await expect(dialog.getByRole('checkbox', { checked: true })).toHaveCount(2);
  const comment = dialog.getByRole('textbox', { name: '补充意见（可选）', exact: true });
  await expect(comment).toHaveAttribute('maxlength', '1000');
  await comment.fill('测'.repeat(1001));
  await expect(comment).toHaveValue('测'.repeat(1000));
  await expect(dialog.getByText('1000/1000', { exact: true })).toBeVisible();
  await dialog.getByRole('checkbox', { name: '检测准确性', exact: true }).uncheck();
  await expect(dialog.getByRole('checkbox', { checked: true })).toHaveCount(1);
});

test('[live-read] feedback cancel resets fields, restores focus and exposes a safe WeChat link', async ({ page }) => {
  await upload(page);
  const trigger = page.getByRole('button', { name: '使用反馈', exact: true });
  let dialog = await feedback(page);
  const group = dialog.getByRole('link', { name: '吐槽微信群', exact: true });
  await expect(group).toHaveAttribute('href', 'https://feedback-chat-5d9.pages.dev/');
  await expect(group).toHaveAttribute('target', '_blank');
  await expect(group).toHaveAttribute('rel', /noopener/);
  await dialog.getByRole('radio', { name: '5 星', exact: true }).focus();
  await dialog.getByRole('radio', { name: '5 星', exact: true }).press('Space');
  await dialog.getByRole('checkbox', { name: '页面设计', exact: true }).check();
  await dialog.getByRole('textbox', { name: '补充意见（可选）', exact: true }).fill('GUI_TEST unsent draft');
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(trigger).toBeFocused();
  dialog = await feedback(page);
  await expect(dialog.getByRole('radio', { checked: true })).toHaveCount(0);
  await expect(dialog.getByRole('checkbox', { checked: true })).toHaveCount(0);
  await expect(dialog.getByRole('textbox', { name: '补充意见（可选）', exact: true })).toHaveValue('');
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
});

test('[live-read] English and Chinese preferences persist across reload and navigation', async ({ page }) => {
  await upload(page);
  let dialog = await settings(page);
  await dialog.getByRole('button', { name: 'English', exact: true }).click();
  // Switching locale changes the dialog's accessible name immediately.
  dialog = page.getByRole('dialog', { name: 'Settings', exact: true });
  await expect(dialog.getByRole('button', { name: 'English', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await dialog.getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Upload thesis', level: 1, exact: true })).toBeVisible();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: 'Upload thesis', level: 1, exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Report history', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Report history', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  dialog = page.getByRole('dialog', { name: 'Settings', exact: true });
  await dialog.getByRole('button', { name: '简体中文', exact: true }).click();
  dialog = page.getByRole('dialog', { name: '设置', exact: true });
  await dialog.getByRole('button', { name: '完成', exact: true }).click();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: '历史报告', exact: true })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem('sjtu-ui-locale'))).toBe('zh');
});

test('[live-read] light, dark and system theme choices persist and follow system appearance', async ({ page }) => {
  await upload(page);
  let dialog = await settings(page);
  await dialog.getByRole('button', { name: '深色', exact: true }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await expect(dialog.getByRole('button', { name: '深色', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await dialog.getByRole('button', { name: '完成', exact: true }).click();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('html')).toHaveClass(/dark/);
  dialog = await settings(page);
  await dialog.getByRole('button', { name: '浅色', exact: true }).click();
  await expect(page.locator('html')).toHaveClass(/light/);
  await page.emulateMedia({ colorScheme: 'dark' });
  await dialog.getByRole('button', { name: '跟随系统', exact: true }).click();
  await expect(page.locator('html')).toHaveClass(/dark/);
  await page.emulateMedia({ colorScheme: 'light' });
  await expect(page.locator('html')).toHaveClass(/light/);
  expect(await page.evaluate(() => localStorage.getItem('sjtu-ui-theme'))).toBe('system');
});

test('[live-read] settings traps keyboard focus and returns focus after close or Escape', async ({ page }) => {
  await upload(page);
  const trigger = page.getByRole('button', { name: '设置', exact: true });
  let dialog = await settings(page);
  await dialog.getByRole('button', { name: '完成', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: '关闭', exact: true })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: '完成', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  dialog = await settings(page);
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
  await expect(trigger).toBeFocused();
});

test('[live-read] history rows match owned reports, columns and saved creation timestamps', async ({ page }) => {
  const reports = await history(page);
  test.skip(!reports.length, 'The live student has no saved reports.');
  const table = historyTable(page);
  await expect(table.getByRole('columnheader')).toHaveText(['文档名称', '检测类型', '检测结果', '报告生成时间', '操作']);
  expect(await rowNames(table)).toEqual(reports.slice(0, 5).map(report => report.source_filename));
  const first = table.locator('tbody tr').first();
  await expect(first.locator('time')).toHaveAttribute('datetime', reports[0].created_at);
  await expect(first.locator('time')).toContainText(/\d{2}:\d{2}:\d{2}/);
  await expect(first.getByRole('link', { name: '查看详情', exact: true })).toHaveAttribute('href', `/reports/pdf/${encodeURIComponent(reports[0].id)}`);
  await expect(first.getByRole('link', { name: '增量补跑', exact: true })).toHaveAttribute('href', `/reports/pdf/${encodeURIComponent(reports[0].id)}?rerun=1`);
  await expect(first.getByText(`错误总数：${reports[0].summary.finding_count}`, { exact: true })).toBeVisible();
});

test('[live-read] history search trims and ignores case, with a recoverable no-results state', async ({ page }) => {
  const reports = await history(page);
  test.skip(!reports.length, 'The live student has no saved reports.');
  const search = page.getByRole('searchbox', { name: '搜索检测报告', exact: true });
  const query = reports[0].source_filename.toUpperCase();
  await search.fill(`  ${query}  `);
  const matching = reports.filter(report => report.source_filename.toLowerCase().includes(query.toLowerCase()));
  expect(await rowNames(historyTable(page))).toEqual(matching.slice(0, 5).map(report => report.source_filename));
  await search.fill('GUI_TEST_NO_MATCH_87b518e1');
  await expect(page.getByText('未找到匹配的报告', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled();
  await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: '查看全部报告', exact: true }).click();
  await expect(search).toHaveValue('');
  await expect(search).toBeFocused();
  expect(await rowNames(historyTable(page))).toEqual(reports.slice(0, 5).map(report => report.source_filename));
});

test('[live-read] history page sizes render actual rows and return to page one', async ({ page }) => {
  const reports = await history(page);
  test.skip(reports.length <= 5, 'Pagination requires more than five owned reports.');
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  expect(await rowNames(historyTable(page))).toEqual(reports.slice(5, 10).map(report => report.source_filename));
  for (const size of [10, 20, 50, 100, 5]) {
    await pageSize(page, size);
    expect(await rowNames(historyTable(page))).toEqual(reports.slice(0, size).map(report => report.source_filename));
    await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: '第 1 页', exact: true })).toHaveAttribute('aria-current', 'page');
  }
});

test('[live-read] history pager validates drafts, clamps numeric jumps and honors page boundaries', async ({ page }) => {
  const reports = await history(page);
  test.skip(reports.length <= 5, 'Pagination requires more than five owned reports.');
  const pages = Math.ceil(reports.length / 5);
  const jump = page.getByRole('textbox', { name: '跳转页码', exact: true });
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled();
  await jump.fill('abc');
  await jump.press('Enter');
  await expect(jump).toHaveValue('1');
  await jump.fill('999999');
  await jump.press('Enter');
  await expect(jump).toHaveValue(String(pages));
  await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled();
  expect(await rowNames(historyTable(page))).toEqual(reports.slice((pages - 1) * 5).map(report => report.source_filename));
  await jump.fill('0');
  await jump.blur();
  await expect(jump).toHaveValue('1');
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await expect(jump).toHaveValue('2');
  await page.getByRole('button', { name: '上一页', exact: true }).click();
  await expect(jump).toHaveValue('1');
});

test('[live-read] batch selection distinguishes this page from all owned reports', async ({ page }) => {
  const reports = await history(page);
  test.skip(!reports.length, 'Batch management requires saved reports.');
  await page.getByRole('button', { name: '批量管理', exact: true }).click();
  await expect(selectedExport(page, 0)).toBeDisabled();
  const count = Math.min(reports.length, 5);
  const pageCheckbox = page.getByRole('checkbox', { name: '全选报告', exact: true });
  await pageCheckbox.check();
  await expect(selectedExport(page, count)).toBeEnabled();
  await expect(historyTable(page).getByRole('checkbox', { checked: true })).toHaveCount(count + 1);
  await page.getByRole('button', { name: '清空选择', exact: true }).click();
  const first = historyTable(page).getByRole('checkbox', { name: /^选择报告：/ }).first();
  await first.check();
  if (count > 1) await expect(pageCheckbox).toHaveJSProperty('indeterminate', true);
  await page.getByRole('button', { name: '全选全部报告', exact: true }).click();
  await expect(selectedExport(page, reports.length)).toBeEnabled();
  if (reports.length > 5) {
    await page.getByRole('button', { name: '下一页', exact: true }).click();
    await expect(pageCheckbox).toBeChecked();
    await expect(selectedExport(page, reports.length)).toBeEnabled();
  }
});

test('[live-read] changing search clears hidden selections and ending management clears all selections', async ({ page }) => {
  const reports = await history(page);
  test.skip(!reports.length, 'Batch management requires saved reports.');
  await page.getByRole('button', { name: '批量管理', exact: true }).click();
  await page.getByRole('button', { name: '全选全部报告', exact: true }).click();
  await expect(selectedExport(page, reports.length)).toBeEnabled();
  await page.getByRole('searchbox', { name: '搜索检测报告', exact: true }).fill(reports[0].source_filename);
  await expect(selectedExport(page, 0)).toBeDisabled();
  await page.getByRole('button', { name: '全选搜索结果', exact: true }).click();
  const count = reports.filter(report => report.source_filename.toLowerCase().includes(reports[0].source_filename.toLowerCase())).length;
  await expect(selectedExport(page, count)).toBeEnabled();
  await page.getByRole('button', { name: '完成管理', exact: true }).click();
  await expect(page.getByRole('region', { name: '批量管理', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '批量管理', exact: true }).click();
  await expect(selectedExport(page, 0)).toBeDisabled();
});

test('[live-read] single report deletion can be cancelled by button or Escape without any DELETE', async ({ page }) => {
  const reports = await history(page);
  test.skip(!reports.length, 'Delete cancellation requires a saved report.');
  const deletes = [];
  page.on('request', request => { if (request.method() === 'DELETE') deletes.push(request.url()); });
  const table = historyTable(page);
  const before = await rowNames(table);
  const trigger = table.locator('tbody tr').first().getByRole('button', { name: '删除报告', exact: true });
  await trigger.click();
  let dialog = page.getByRole('alertdialog', { name: '删除报告？', exact: true });
  await expect(dialog.getByText(reports[0].source_filename, { exact: true })).toBeVisible();
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(trigger).toBeFocused();
  expect(await rowNames(table)).toEqual(before);
  await trigger.click();
  dialog = page.getByRole('alertdialog', { name: '删除报告？', exact: true });
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  expect(deletes).toEqual([]);
});

test('[live-read] batch deletion cancellation preserves selected reports without deleting', async ({ page }) => {
  const reports = await history(page);
  test.skip(reports.length < 2, 'Plural deletion cancellation requires two saved reports.');
  const deletes = [];
  page.on('request', request => { if (request.method() === 'DELETE') deletes.push(request.url()); });
  await page.getByRole('button', { name: '批量管理', exact: true }).click();
  const choices = historyTable(page).getByRole('checkbox', { name: /^选择报告：/ });
  await choices.nth(0).check();
  await choices.nth(1).check();
  await page.getByRole('button', { name: '删除选中（2）', exact: true }).click();
  const dialog = page.getByRole('alertdialog', { name: '删除选中的报告？', exact: true });
  await expect(dialog).toContainText('已选择 2 份报告');
  await dialog.getByRole('button', { name: '取消', exact: true }).click();
  await expect(choices.nth(0)).toBeChecked();
  await expect(choices.nth(1)).toBeChecked();
  await expect(selectedExport(page, 2)).toBeEnabled();
  expect(deletes).toEqual([]);
});

test('[live-read] desktop sidebar collapses and expands while retaining navigation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await upload(page);
  const sidebar = page.locator('[data-slot="sidebar"][data-state]');
  await expect(sidebar).toHaveAttribute('data-state', 'expanded');
  await page.getByRole('button', { name: '切换主导航', exact: true }).click();
  await expect(sidebar).toHaveAttribute('data-state', 'collapsed');
  await page.getByRole('link', { name: '历史报告', exact: true }).click();
  await expect(page.getByRole('heading', { name: '历史报告', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '切换主导航', exact: true }).click();
  await expect(sidebar).toHaveAttribute('data-state', 'expanded');
  await assertLayout(page);
});

test('[live-read] mobile navigation closes after route selection and keeps the history viewport usable', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await upload(page);
  await page.getByRole('button', { name: '切换主导航', exact: true }).click();
  const menu = page.getByRole('dialog', { name: '主导航', exact: true });
  await expect(menu).toBeVisible();
  await menu.getByRole('link', { name: '历史报告', exact: true }).click();
  await expect(menu).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '历史报告', exact: true })).toBeVisible();
  await assertLayout(page);
  await page.getByRole('button', { name: '切换主导航', exact: true }).click();
  await expect(menu).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
});

test('[live-read] Chinese and English expanded upload layouts preserve rule order and controls', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await upload(page);
  await expandRules(page);
  const original = await ruleSection(page).locator('.credit-rule-name').allTextContents();
  await assertLayout(page);
  const dialog = await settings(page);
  await dialog.getByRole('button', { name: 'English', exact: true }).click();
  await page.getByRole('dialog', { name: 'Settings', exact: true }).getByRole('button', { name: 'Done', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Upload thesis', level: 1, exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Collapse checks', exact: true })).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('section[aria-label="Select review checks"] .credit-rule-name')).toHaveCount(original.length);
  const english = await page.locator('section[aria-label="Content checks"] .credit-rule-name').allTextContents();
  expect(english).toEqual(['Chinese character errors', 'Bilingual abstract agreement', 'Bilingual keyword match', 'Chinese/English punctuation']);
  await expect(page.getByRole('button', { name: 'Start review', exact: true })).toBeVisible();
  await assertLayout(page);
});

test('[live-read] student upload, history and mobile settings pass accessibility and layout checks', async ({ page }, testInfo) => {
  await upload(page);
  await checkA11y(page, testInfo);
  await history(page);
  await checkA11y(page, testInfo);
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, '/paper-upload');
  await expect(page.getByRole('heading', { name: '论文上传', exact: true })).toBeVisible();
  await expandRules(page);
  await assertLayout(page);
  await settings(page);
  await checkA11y(page, testInfo);
  await assertLayout(page);
});
