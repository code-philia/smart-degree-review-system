const { test, expect, open, readyTable, assertLayout, checkA11y } = require('../support.cjs');

test.use({ role: 'admin' });

const reportTable = '全部用户检测报告';
const feedbackTable = '全部用户反馈';
const listPattern = resource => new RegExp(`/api/supervision/${resource}(?:\\?|$)`);
const reportHref = item => `/admin/reports/${encodeURIComponent(item.id)}${item.report_type && item.report_type !== 'paper_lint' ? `?type=${item.report_type}` : ''}`;
const note = (info, description) => info.annotations.push({ type: 'coverage', description });
// Setup reads 50 records per request; the console intentionally displays 20.
const firstUiPage = data => ({ ...data, items: data.items.slice(0, 20), page_size: 20 });
const emptyStatus = table => table.getByRole('status').filter({ hasText: '暂无匹配记录' });

async function readAfter(page, resource, params, action) {
  const pending = page.waitForResponse(response => {
    const url = new URL(response.url());
    return url.pathname === `/api/supervision/${resource}` && response.status() === 200
      && Object.entries(params).every(([key, value]) => url.searchParams.get(key) === String(value));
  });
  await action();
  const data = await (await pending).json();
  await readyTable(page, resource === 'reports' ? reportTable : feedbackTable);
  return data;
}

async function expectRows(page, name, data) {
  const table = page.getByRole('table', { name, exact: true });
  if (!data.items.length) {
    await expect(emptyStatus(table)).toBeVisible();
    return;
  }
  const rows = table.locator('tbody > tr');
  await expect(rows).toHaveCount(data.items.length);
  for (let index = 0; index < data.items.length; index++) {
    const item = data.items[index], row = rows.nth(index);
    if (name === reportTable) {
      await expect(row).toContainText(item.source_filename);
      await expect(row.getByRole('link', { name: '查看报告', exact: true })).toHaveAttribute('href', reportHref(item));
      await expect(row).toContainText(item.owner.username);
    } else {
      await expect(row).toContainText(item.type_label);
      await expect(row).toContainText(item.username);
      await expect(row).toContainText(item.feedback_label);
    }
  }
}

function sampleReport(index, overrides = {}) {
  return {
    id: `gui-readonly-${index}`, report_type: 'paper_lint', type_label: '论文规范检测',
    source_filename: `只读注入论文-${index}.pdf`, created_at: '2026-11-24T08:00:00.000Z',
    owner: { id: 'gui-owner', username: 'gui-owner-account', display_name: '注入用户姓名' },
    summary: { finding_count: 0, error_finding_count: 0, warning_finding_count: 0, info_finding_count: 0 },
    ...overrides,
  };
}

function sampleFeedback(index, overrides = {}) {
  return {
    id: `gui-feedback-${index}`, type: 'finding', type_label: '检测结果评价',
    user_id: 'gui-owner', username: 'gui-feedback-account', display_name: '反馈用户姓名',
    report_id: 'gui-readonly-1', source_filename: '关联论文专属词.pdf', rule_id: 'gui_rule_15', rule_title: '注入规则',
    finding_text: '这是已保存的检测描述。', feedback_value: 'negative', feedback_label: '点踩',
    reason_label: '误报', reason_text: '反馈正文专属词', comment: null, satisfaction_score: null,
    improvement_labels: [], generation: null, saved_suggestion: null,
    created_at: '2026-11-24T08:00:00.000Z', updated_at: '2026-11-24T08:00:00.000Z',
    ...overrides,
  };
}

async function injectList(page, resource, resolve) {
  await page.route(listPattern(resource), async route => {
    const params = new URL(route.request().url()).searchParams;
    const result = typeof resolve === 'function' ? resolve(params) : resolve;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(result) });
  });
}

function paginated(items, params) {
  const page = Number(params.get('page') || 1);
  return { items: items.slice((page - 1) * 20, page * 20), total: items.length, page, page_size: 20 };
}

test('[live-read] administrator overview and report rows agree with saved data', async ({ page, facts }) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  await expect(page.getByRole('heading', { name: '全部报告', exact: true })).toBeVisible();
  await expect(page.getByRole('navigation', { name: '监管导航' }).getByRole('link', { name: '报告监管' })).toHaveAttribute('aria-current', 'page');
  await expectRows(page, reportTable, firstUiPage(facts.adminReports));
  await expect(page.getByRole('region', { name: '监管数据概览' })).toContainText('用户总数');
  await expect(page.getByRole('region', { name: '监管数据概览' })).toContainText('负面反馈');
  await expect(page.getByText(/数据更新于.*北京时间/)).toBeVisible();
});

for (const [field, label, obtain] of [
  ['filename', '论文名称', item => item.source_filename],
  ['display_name', '用户姓名', item => item.owner.display_name],
  ['username', '用户账号', item => item.owner.username],
  ['report_id', '报告编号', item => item.id],
]) {
  test(`[live-read] report search uses ${label} only`, async ({ page, facts }, info) => {
    await open(page, '/admin/reports');
    await readyTable(page, reportTable);
    const sample = facts.adminReports.items.find(item => obtain(item));
    const q = sample ? obtain(sample) : 'GUI-NO-EXISTING-DISPLAY-NAME-20261125';
    if (!sample) note(info, `No existing report exposes ${field}; this live case verifies its empty result and injected cases cover a positive match.`);
    if (field !== 'filename') {
      await readAfter(page, 'reports', { search_field: field }, () => page.getByLabel('报告搜索类别').selectOption(field));
    }
    const data = await readAfter(page, 'reports', { search_field: field, q, page: 1 }, () => page.getByRole('searchbox', { name: '搜索报告' }).fill(`  ${q}  `));
    await expectRows(page, reportTable, data);
    if (sample) {
      expect(data.total).toBeGreaterThan(0);
      expect(data.items.every(item => String(obtain(item) || '').toLowerCase().includes(q.toLowerCase()))).toBe(true);
    } else expect(data.total).toBe(0);
  });
}

test('[live-read] report no-match search and clearing recover the original list', async ({ page, facts }) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  const query = 'GUI-NO-MATCH-20261125-6F239831';
  const empty = await readAfter(page, 'reports', { q: query }, () => page.getByRole('searchbox', { name: '搜索报告' }).fill(query));
  expect(empty.total).toBe(0);
  await expectRows(page, reportTable, empty);
  const restored = await readAfter(page, 'reports', { q: '' }, () => page.getByRole('searchbox', { name: '搜索报告' }).fill(''));
  expect(restored.total).toBe(facts.adminReports.total);
  await expectRows(page, reportTable, restored);
});

test('[live-read] every report type filter returns its own saved report category', async ({ page }, info) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  for (const type of ['paper_lint', 'normative', 'duplication', 'example', 'all']) {
    const data = await readAfter(page, 'reports', { type, page: 1 }, () => page.getByLabel('报告类型').selectOption(type));
    await expectRows(page, reportTable, data);
    if (type !== 'all') expect(data.items.every(item => item.report_type === type)).toBe(true);
    if (!data.total) note(info, `No existing ${type} reports; the live empty state passed and legacy rendering is covered with injected saved data.`);
  }
});

test('[live-read] report pagination respects the existing record count and returns to page one', async ({ page, facts }, info) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled();
  if (facts.adminReports.total <= 20) {
    await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled();
    note(info, `Only ${facts.adminReports.total} existing reports: real pagination cannot advance; injected 23-record coverage checks transitions.`);
  } else {
    const second = await readAfter(page, 'reports', { page: 2 }, () => page.getByRole('button', { name: '下一页', exact: true }).click());
    await expectRows(page, reportTable, second);
    const firstIds = new Set(firstUiPage(facts.adminReports).items.map(item => `${item.report_type}:${item.id}`));
    expect(second.items.every(item => !firstIds.has(`${item.report_type}:${item.id}`))).toBe(true);
    const first = await readAfter(page, 'reports', { page: 1 }, () => page.getByRole('button', { name: '上一页', exact: true }).click());
    await expectRows(page, reportTable, first);
    expect(first.items.map(item => `${item.report_type}:${item.id}`)).toEqual(firstUiPage(facts.adminReports).items.map(item => `${item.report_type}:${item.id}`));
  }
});

test('[injected] report pagination reaches its last page and a filter resets page one', async ({ page }) => {
  const items = Array.from({ length: 23 }, (_, index) => sampleReport(index + 1));
  await injectList(page, 'reports', params => paginated(params.get('q') ? items.slice(0, 1) : items, params));
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  await expect(page.getByRole('table', { name: reportTable }).locator('tbody > tr')).toHaveCount(20);
  await readAfter(page, 'reports', { page: 2 }, () => page.getByRole('button', { name: '下一页', exact: true }).click());
  await expect(page.getByRole('table', { name: reportTable }).locator('tbody > tr')).toHaveCount(3);
  await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled();
  await readAfter(page, 'reports', { page: 1, q: '只读注入论文-1' }, () => page.getByRole('searchbox', { name: '搜索报告' }).fill('只读注入论文-1'));
  await expect(page.locator('.sup-pagination')).toContainText('第 1 / 1 页');
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled();
});

test('[injected] owner search does not leak into filename search', async ({ page }) => {
  const report = sampleReport(1);
  await injectList(page, 'reports', params => {
    const matched = !params.get('q') || (params.get('search_field') === 'display_name' && params.get('q') === report.owner.display_name);
    return paginated(matched ? [report] : [], params);
  });
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  await readAfter(page, 'reports', { search_field: 'filename', q: report.owner.display_name }, () => page.getByRole('searchbox', { name: '搜索报告' }).fill(report.owner.display_name));
  await expect(emptyStatus(page.getByRole('table', { name: reportTable }))).toBeVisible();
  const matched = await readAfter(page, 'reports', { search_field: 'display_name', q: report.owner.display_name }, () => page.getByLabel('报告搜索类别').selectOption('display_name'));
  await expectRows(page, reportTable, matched);
});

test('[live-read] feedback type filters retain every saved category', async ({ page }, info) => {
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  for (const type of ['system', 'finding', 'suggestion', 'all']) {
    const data = await readAfter(page, 'feedback', { type, page: 1 }, () => page.getByLabel('反馈类型').selectOption(type));
    await expectRows(page, feedbackTable, data);
    if (type !== 'all') expect(data.items.every(item => item.type === type)).toBe(true);
    if (!data.total) note(info, `No existing ${type} feedback; live empty state checked and injected details cover the missing category.`);
  }
});

test('[live-read] feedback sentiment filters classify scores and votes correctly', async ({ page }) => {
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  for (const value of ['negative', 'positive', 'all']) {
    const data = await readAfter(page, 'feedback', { value, page: 1 }, () => page.getByLabel('反馈评价').selectOption(value));
    await expectRows(page, feedbackTable, data);
    if (value === 'negative') expect(data.items.every(item => item.feedback_value === 'negative' || (item.type === 'system' && item.satisfaction_score <= 2))).toBe(true);
    if (value === 'positive') expect(data.items.every(item => item.feedback_value === 'positive' || (item.type === 'system' && item.satisfaction_score >= 4))).toBe(true);
  }
});

test('[injected] feedback pagination and sentiment changes reset to page one', async ({ page }) => {
  const items = Array.from({ length: 23 }, (_, index) => sampleFeedback(index + 1));
  await injectList(page, 'feedback', params => paginated(params.get('value') === 'positive' ? [] : items, params));
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  await readAfter(page, 'feedback', { page: 2 }, () => page.getByRole('button', { name: '下一页', exact: true }).click());
  await expect(page.getByRole('table', { name: feedbackTable }).locator('tbody > tr')).toHaveCount(3);
  await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeDisabled();
  const empty = await readAfter(page, 'feedback', { page: 1, value: 'positive' }, () => page.getByLabel('反馈评价').selectOption('positive'));
  await expectRows(page, feedbackTable, empty);
  await expect(page.getByRole('button', { name: '上一页', exact: true })).toBeDisabled();
});

test('[injected] every feedback search field sends the selected category and literal query', async ({ page }) => {
  const item = sampleFeedback(1);
  const queries = { content: item.reason_text, filename: item.source_filename, display_name: item.display_name, username: item.username, rule_id: item.rule_id };
  await injectList(page, 'feedback', params => paginated(!params.get('q') || queries[params.get('search_field')] === params.get('q') ? [item] : [], params));
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  for (const [field, q] of [['content', item.reason_text], ['filename', item.source_filename], ['display_name', item.display_name], ['username', item.username], ['rule_id', item.rule_id]]) {
    if (field !== 'content') await readAfter(page, 'feedback', { search_field: field }, () => page.getByLabel('反馈搜索类别').selectOption(field));
    const data = await readAfter(page, 'feedback', { search_field: field, q }, () => page.getByRole('searchbox', { name: '搜索反馈' }).fill(q));
    expect(data.total).toBe(1);
    await expectRows(page, feedbackTable, data);
  }
  const query = 'GUI-NO-MATCH-20261125';
  const empty = await readAfter(page, 'feedback', { q: query }, () => page.getByRole('searchbox', { name: '搜索反馈' }).fill(query));
  expect(empty.total).toBe(0);
  await expectRows(page, feedbackTable, empty);
});

test('[live-read] feedback details show saved text and preserve their exact report links', async ({ page, facts }, info) => {
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  if (!facts.adminFeedback.items.length) {
    await expect(emptyStatus(page.getByRole('table', { name: feedbackTable }))).toBeVisible();
    note(info, 'No existing feedback details; deterministic injected tests exercise all detail variants.');
    return;
  }
  const item = facts.adminFeedback.items[0];
  const trigger = page.getByRole('button', { name: '查看反馈详情', exact: true }).first();
  await trigger.click();
  const dialog = page.getByRole('dialog', { name: '反馈详情' });
  await expect(dialog).toContainText(item.username);
  await expect(dialog).toContainText(item.feedback_label);
  if (item.type === 'system') await expect(dialog).toContainText(item.comment || '未填写补充说明');
  else {
    await expect(dialog).toContainText(item.reason_label || '未选择原因');
    if (item.reason_text) await expect(dialog).toContainText(item.reason_text);
    if (item.finding_text) await expect(dialog).toContainText(item.finding_text);
  }
  if (item.report_id) await expect(dialog.getByRole('link', { name: '查看关联报告' })).toHaveAttribute('href', `/admin/reports/${encodeURIComponent(item.report_id)}`);
  else await expect(dialog.getByRole('link', { name: '查看关联报告' })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(trigger).toBeFocused();
});

test('[injected] system feedback renders literal unsafe-looking text and improvement labels safely', async ({ page }) => {
  const comment = '<script>GUI_AUDIT_SCRIPT_MUST_REMAIN_TEXT</script> & 原始意见';
  const item = sampleFeedback(1, { type: 'system', type_label: '使用反馈', report_id: null, feedback_value: null, feedback_label: '3 分', satisfaction_score: 3, comment, improvement_labels: ['检测准确性', '页面设计'] });
  await injectList(page, 'feedback', { items: [item], total: 1, page: 1, page_size: 20 });
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  await page.getByRole('button', { name: '查看反馈详情' }).click();
  const dialog = page.getByRole('dialog', { name: '反馈详情' });
  await expect(dialog.getByText(comment, { exact: true })).toBeVisible();
  await expect(dialog).toContainText('检测准确性');
  await expect(dialog).toContainText('页面设计');
  await expect(dialog.getByRole('link', { name: '查看关联报告' })).toHaveCount(0);
  await expect(page.locator('script').filter({ hasText: 'GUI_AUDIT_SCRIPT_MUST_REMAIN_TEXT' })).toHaveCount(0);
});

test('[injected] suggestion feedback displays the evaluated saved version without regeneration', async ({ page }) => {
  const item = sampleFeedback(1, { type: 'suggestion', type_label: '修复建议评价', generation: 2,
    saved_suggestion: { id: 'saved-version-2', generation: 2, status: 'suggested', actions: [{ instruction: '这是用户评价的第二版已保存建议。' }] } });
  const writes = [];
  page.on('request', request => { if (request.method() !== 'GET' && request.url().includes('/api/')) writes.push(request.url()); });
  await injectList(page, 'feedback', { items: [item], total: 1, page: 1, page_size: 20 });
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  await page.getByRole('button', { name: '查看反馈详情' }).click();
  const dialog = page.getByRole('dialog', { name: '反馈详情' });
  await expect(dialog).toContainText('第 2 版');
  await expect(dialog).toContainText(item.saved_suggestion.actions[0].instruction);
  await expect(dialog.getByRole('link', { name: '查看关联报告' })).toHaveAttribute('href', '/admin/reports/gui-readonly-1');
  await page.getByRole('button', { name: '关闭反馈详情' }).click();
  expect(writes).toEqual([]);
});

test('[injected] missing saved suggestion still identifies its evaluated version', async ({ page }) => {
  const item = sampleFeedback(1, { type: 'suggestion', type_label: '修复建议评价', generation: 7 });
  await injectList(page, 'feedback', { items: [item], total: 1, page: 1, page_size: 20 });
  await open(page, '/admin/feedback');
  await readyTable(page, feedbackTable);
  await page.getByRole('button', { name: '查看反馈详情' }).click();
  await expect(page.getByRole('dialog', { name: '反馈详情' })).toContainText('第 7 版，具体建议暂不可读取。');
});

test('[injected] legacy report links keep colliding IDs distinct and show saved results', async ({ page }) => {
  const labels = { normative: '早期规范检测', duplication: '查重检测', example: '示例规则检测' };
  const items = Object.entries(labels).map(([type, label]) => sampleReport(1, { report_type: type, type_label: label, summary: null }));
  await injectList(page, 'reports', { items, total: 3, page: 1, page_size: 20 });
  await page.route(/\/api\/supervision\/reports\/gui-readonly-1(?:\?|$)/, async route => {
    const type = new URL(route.request().url()).searchParams.get('type');
    await route.fulfill({ json: { owner: items[0].owner, legacy: { id: items[0].id, report_type: type, type_label: labels[type], source_filename: items[0].source_filename, created_at: items[0].created_at, original_text: `历史原文-${type}`, saved_result: { summary: `已保存结果-${type}`, findings: [] }, has_pdf: type === 'example' } } });
  });
  for (const type of Object.keys(labels)) {
    await open(page, '/admin/reports');
    await readyTable(page, reportTable);
    const row = page.getByRole('table', { name: reportTable }).getByRole('row').filter({ hasText: labels[type] });
    await row.getByRole('link', { name: '查看报告', exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`/admin/reports/gui-readonly-1\\?type=${type}$`));
    await expect(page.getByRole('heading', { name: '已保存的检测结果' })).toBeVisible();
    await expect(page.getByText(`历史原文-${type}`, { exact: true })).toBeVisible();
    await expect(page.getByText(`已保存结果-${type}`, { exact: true })).toBeVisible();
    await expect(page.getByText('只读查看', { exact: true })).toBeVisible();
    const pdf = page.getByRole('link', { name: '查看原始 PDF' });
    if (type === 'example') await expect(pdf).toHaveAttribute('href', '/api/supervision/reports/gui-readonly-1/pdf?type=example');
    else await expect(pdf).toHaveCount(0);
  }
});

test('[injected] missing report gives a recoverable state and list navigation', async ({ page }) => {
  await page.route(/\/api\/supervision\/reports\/gui-missing(?:\?|$)/, route => route.fulfill({ status: 404, json: { message: '未找到该审查报告' } }));
  await open(page, '/admin/reports/gui-missing');
  await expect(page.getByRole('heading', { name: '报告暂不可读取' })).toBeVisible();
  await page.getByRole('link', { name: '返回全部报告' }).click();
  await readyTable(page, reportTable);
});

test('[live-read] English query and uppercase administrator routes remain Chinese', async ({ page }) => {
  for (const path of ['/ADMIN/reports?lang=en', '/admin/feedback?lang=en']) {
    await open(page, path);
    await readyTable(page, path.includes('feedback') ? feedbackTable : reportTable);
    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
    await expect(page.getByRole('navigation', { name: '监管导航' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'EN', exact: true })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: path.includes('feedback') ? '全部反馈' : '全部报告', exact: true })).toBeVisible();
  }
});

test('[live-read] appearance persists across reload without changing report data', async ({ page, facts }) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  const dark = await page.locator('html').getAttribute('class');
  if (dark && dark.split(/\s+/).includes('dark')) await page.getByRole('button', { name: '切换到浅色模式' }).click();
  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveClass(/\bdark\b/);
  await page.reload();
  await readyTable(page, reportTable);
  await expect(page.getByRole('button', { name: '切换到浅色模式' })).toBeVisible();
  await expectRows(page, reportTable, firstUiPage(facts.adminReports));
  await page.getByRole('button', { name: '切换到浅色模式' }).click();
  await expect(page.locator('html')).not.toHaveClass(/\bdark\b/);
});

test('[injected] logout clears the UI session without revoking the shared live test session', async ({ page }) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  await page.route('**/api/auth/logout', route => route.fulfill({ status: 204, body: '' }));
  await page.route('**/api/auth/me', route => route.fulfill({ status: 401, json: { message: 'Authentication required' } }));
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page.getByRole('heading', { name: '管理员登录', exact: true })).toBeVisible();
  await open(page, '/admin/feedback');
  await expect(page).toHaveURL(/\/admin\/login$/);
  await expect(page.getByRole('table', { name: feedbackTable })).toHaveCount(0);
});

test('[live-read] report and feedback lists expose viewing controls without mutation controls', async ({ page }) => {
  const writes = [];
  page.on('request', request => { if (request.method() !== 'GET' && request.url().includes('/api/')) writes.push(`${request.method()} ${request.url()}`); });
  for (const [path, table] of [['/admin/reports', reportTable], ['/admin/feedback', feedbackTable]]) {
    await open(page, path);
    await readyTable(page, table);
    await expect(page.getByRole('button', { name: /删除|开始检测|重新检测|生成修复|标记为已处理|取消评价/ })).toHaveCount(0);
  }
  expect(writes).toEqual([]);
});

test('[live-read] saved report details remain Chinese and read-only with PDF recovery controls', async ({ page, facts }, info) => {
  const report = facts.adminReports.items.find(item => !item.report_type || item.report_type === 'paper_lint');
  if (!report) {
    await open(page, '/admin/reports');
    await readyTable(page, reportTable);
    await expect(page.getByLabel('报告类型')).toBeVisible();
    note(info, 'No existing paper-lint report is available on the captured first page; shared PDF tests cover the viewer with their available report.');
    return;
  }
  await page.route(new RegExp(`/api/supervision/reports/${encodeURIComponent(report.id)}/pdf(?:\\?|$)`), route => route.fulfill({ status: 410, contentType: 'text/plain', body: 'GUI audit: PDF download is covered separately.' }));
  await open(page, `${reportHref(report)}?lang=en`);
  await expect(page.getByRole('heading', { name: report.source_filename, exact: true })).toBeVisible();
  await expect(page.getByText('只读查看', { exact: true })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN');
  await expect(page.getByRole('heading', { name: '检测结果', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: /标记为已处理|生成修复建议|重新生成|取消评价/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '重新加载 PDF', exact: true })).toBeVisible();
  await expect(page.getByRole('link', { name: '打开完整 PDF', exact: true })).toHaveAttribute('href', new RegExp(`/api/supervision/reports/${encodeURIComponent(report.id)}/pdf(?:#page=\\d+)?$`));
  await page.getByRole('link', { name: '返回全部报告' }).click();
  await readyTable(page, reportTable);
});

for (const width of [390, 768, 1440]) {
  test(`[live-read] administrator lists remain usable at ${width}px in light and dark modes`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    for (const [path, table] of [['/admin/reports', reportTable], ['/admin/feedback', feedbackTable]]) {
      await open(page, path);
      await readyTable(page, table);
      await assertLayout(page);
      await expect(page.getByRole('button', { name: '退出登录', exact: true })).toBeInViewport();
      await expect(page.getByRole('button', { name: '下一页', exact: true })).toBeVisible();
      const toggle = page.getByRole('button', { name: /切换到[深浅]色模式/ });
      await toggle.click();
      await assertLayout(page);
    }
  });
}

test('[live-read] administrator tables and feedback dialog pass serious accessibility checks', async ({ page, facts }, info) => {
  await open(page, '/admin/reports');
  await readyTable(page, reportTable);
  await checkA11y(page, info);
  await page.getByRole('link', { name: '反馈监管', exact: true }).click();
  await readyTable(page, feedbackTable);
  await checkA11y(page, info);
  if (facts.adminFeedback.items.length) {
    await page.getByRole('button', { name: '查看反馈详情' }).first().click();
    await expect(page.getByRole('dialog', { name: '反馈详情' })).toBeVisible();
    await checkA11y(page, info);
  } else note(info, 'Live feedback table is empty; injected dialog tests cover keyboard and content behavior.');
});

test.describe('administrator entry without a session', () => {
  test.use({ role: 'guest' });

  test('[injected] administrator login displays a server error without a real failed password attempt', async ({ page }, info) => {
    await page.route('**/api/auth/supervision-login', route => route.fulfill({ status: 401, json: { message: '账号或密码错误' } }));
    await open(page, '/admin/login?lang=en');
    await expect(page.getByRole('heading', { name: '管理员登录', exact: true })).toBeVisible();
    await expect(page.getByLabel('账号', { exact: true })).toHaveValue('admin');
    await expect(page.getByLabel('密码', { exact: true })).toHaveAttribute('type', 'password');
    await page.getByLabel('密码', { exact: true }).fill('GUI-injected-not-a-real-password');
    await page.getByRole('button', { name: '登录监管台' }).click();
    await expect(page.getByRole('alert')).toHaveText('账号或密码错误');
    await expect(page.getByRole('button', { name: '登录监管台' })).toBeEnabled();
    await expect(page.getByRole('link', { name: /jAccount/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'EN', exact: true })).toHaveCount(0);
    await checkA11y(page, info);
  });
});
