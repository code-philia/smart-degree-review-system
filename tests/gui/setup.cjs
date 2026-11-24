const { chromium, request } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { OUT, BASE, MANIFEST, RUN, REGISTRY, state, record } = require('./paths.cjs');
const { installGuard } = require('./guard.cjs');
async function responseJson(response) {
  if (!response.ok()) throw new Error('Setup endpoint returned ' + response.status() + ': ' + new URL(response.url()).pathname);
  return response.json();
}
module.exports = async () => {
  fs.mkdirSync(path.join(OUT, '.auth'), { recursive: true });
  if (!fs.existsSync(RUN)) fs.writeFileSync(RUN, JSON.stringify({ prefix: 'GUI_TEST_' + new Date().toISOString().replace(/\D/g, '').slice(0, 14) + '_' + crypto.randomBytes(3).toString('hex'), started_at: new Date().toISOString(), base_url: BASE }));
  if (!fs.existsSync(REGISTRY)) fs.writeFileSync(REGISTRY, '');
  const password = process.env.GUI_PASSWORD;
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const contexts = {}, auth = [];
  try {
    for (const [role, username] of [['student', 'student01'], ['admin', 'admin'], ['school', 'school_admin01']]) {
      const context = await browser.newContext({ baseURL: BASE, locale: 'zh-CN', timezoneId: 'Asia/Shanghai', viewport: { width: 1440, height: 1000 }, storageState: fs.existsSync(state(role)) ? state(role) : undefined });
      contexts[role] = context;
      await installGuard(context);
      const me = await context.request.get('/api/auth/me');
      if (me.ok() && (await me.json()).user.username === username) {
        auth.push({ role, mode: 'reused-valid-isolated-run-session' });
      } else {
        if (!password) throw new Error('Set GUI_PASSWORD to the assigned local-account password; no password is stored in scripts');
        const page = await context.newPage();
        await page.goto(role === 'admin' ? '/admin/login' : '/auth', { waitUntil: 'domcontentloaded', timeout: 35_000 });
        if (role !== 'admin') await page.getByRole('button', { name: '上海交通大学校徽', exact: true }).click();
        await page.getByLabel('账号', { exact: true }).fill(username);
        await page.getByLabel('密码', { exact: true }).fill(password);
        await page.getByRole('button', { name: role === 'admin' ? '登录监管台' : '登录', exact: true }).click();
        await page.waitForURL(role === 'admin' ? '**/admin/reports' : '**/paper-upload', { timeout: 30_000 });
        const current = await responseJson(await context.request.get('/api/auth/me'));
        if (current.user.username !== username) throw new Error('Wrong setup account identity');
        await context.storageState({ path: state(role) });
        await page.screenshot({ path: path.join(OUT, 'setup-' + role + '.png') });
        auth.push({ role, mode: 'actual-browser-login', username });
        await page.close();
      }
    }
    const studentUser = (await responseJson(await contexts.student.request.get('/api/auth/me'))).user;
    const adminUser = (await responseJson(await contexts.admin.request.get('/api/auth/me'))).user;
    const studentReports = await responseJson(await contexts.student.request.get('/api/normative/paper-lint/reports'));
    const catalog = await responseJson(await contexts.student.request.get('/api/normative/paper-lint/rules?mvp_only=1'));
    const credit = await responseJson(await contexts.student.request.get('/api/normative/paper-lint/credit'));
    const adminReports = await responseJson(await contexts.admin.request.get('/api/supervision/reports?page_size=50'));
    const adminFeedback = await responseJson(await contexts.admin.request.get('/api/supervision/feedback?page_size=50'));
    const summary = await responseJson(await contexts.admin.request.get('/api/supervision/summary'));
    const allReports = [...adminReports.items];
    for (let page = 2; allReports.length < adminReports.total; page++) allReports.push(...(await responseJson(await contexts.admin.request.get('/api/supervision/reports?page_size=50&page=' + page))).items);
    const allowed = new Set(catalog.rules.map(rule => rule.rule_id));
    allowed.add('sjtu_rule_32'); // Historical selections retain the now-hidden retired rule.
    const visible = studentReports.records.filter(report => report.selected_rule_ids?.every(id => allowed.has(id)));
    let studentReport = visible.find(report => (report.summary?.error_finding_count || 0) + (report.summary?.warning_finding_count || 0) + (report.summary?.info_finding_count || 0) > 0) || visible[0];
    const adminReport = adminReports.items.find(report => report.report_type === 'paper_lint' && report.summary?.finding_count > 0);
    if (!studentReport || !adminReport) throw new Error('No existing reports available for GUI reading tests');
    let studentDetail = await responseJson(await contexts.student.request.get('/api/normative/paper-lint/reports/' + studentReport.id, { timeout: 40_000 }));
    const hasLocation = detail => detail.result.rule_runs.some(r => r.findings?.some(f => Number((f.location || f.anchors?.[0]?.location)?.page_number) > 0));
    if (!hasLocation(studentDetail)) {
      const candidates = visible.filter(r => /论文\.pdf$/.test(r.source_filename) && r.summary?.finding_count > 0).slice(0, 8);
      for (const candidate of candidates) {
        const detail = await responseJson(await contexts.student.request.get('/api/normative/paper-lint/reports/' + candidate.id, { timeout: 40_000 }));
        if (hasLocation(detail)) { studentReport = candidate; studentDetail = detail; break; }
      }
    }
    const page = await contexts.admin.newPage();
    const doc = await page.goto('/admin/login', { waitUntil: 'domcontentloaded' });
    const html = await doc.text();
    const builds = [...html.matchAll(/(?:src|href)="(\/assets\/[^" ]+\.(?:js|css))"/g)].map(m => m[1]);
    const facts = { captured_at: new Date().toISOString(), base_url: BASE, builds, auth, studentUser, adminUser, studentReports, studentReport, studentDetail,
      adminReports, adminFeedback, adminReport, allReports, summary, credit, catalog,
      boundaries: { jaccount_success: 'not covered: no real jAccount identity', translations: 'intercepted to avoid model calls', announcements_and_read_flags: 'intercepted to preserve existing account state', only_marked_data_cleanup: true } };
    fs.writeFileSync(MANIFEST, JSON.stringify(facts, null, 2));
    console.log('GUI setup ready:', JSON.stringify({ builds, reports: summary.reports, feedback: summary.feedback, studentVisibleReports: visible.length, run: JSON.parse(fs.readFileSync(RUN)).prefix }));
  } catch (error) {
    throw new Error(String(error.message).split(password || '\u0000').join('[REDACTED]'));
  } finally { await browser.close(); }
};
