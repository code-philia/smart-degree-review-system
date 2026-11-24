const base = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;
const fs = require('node:fs');
const { installGuard } = require('./guard.cjs');
const paths = require('./paths.cjs');
const test = base.test.extend({
  role: ['guest', { option: true }], allowWrites: [false, { option: true }],
  facts: async ({}, use) => use(paths.facts()),
  storageState: async ({ role }, use) => use(role === 'guest' ? { cookies: [], origins: [] } : paths.state(role)),
  page: async ({ page, context, allowWrites }, use, info) => {
    const audit = [], errors = [], failures = [];
    await installGuard(context, { allowWrites, audit });
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if (response.status() >= 500 && new URL(response.url()).origin === paths.BASE) failures.push({ path: new URL(response.url()).pathname, status: response.status() }); });
    page.on('response', async response => {
      if (!allowWrites || !response.ok()) return;
      const req = response.request(), url = new URL(response.url());
      try {
        if (req.method() === 'POST' && url.pathname === '/api/normative/paper-lint/run' && (url.searchParams.get('filename') || '').startsWith(paths.run().prefix)) {
          const value = await response.json();
          if (value.job_id) paths.record({ kind: 'job', id: value.job_id, filename: url.searchParams.get('filename') });
          if (value.report_id) paths.record({ kind: 'report', id: value.report_id, filename: url.searchParams.get('filename') });
        }
        if (req.method() === 'POST' && url.pathname === '/api/normative/feedback/system-feedback') {
          const input = req.postDataJSON();
          if (input.comment?.startsWith(paths.run().prefix)) { const value = await response.json(); if (value.id) paths.record({ kind: 'system-feedback', id: value.id, comment: input.comment }); }
        }
      } catch { /* teardown also reconciles registered request IDs server-side */ }
    });
    await use(page);
    await info.attach('request-boundaries.json', { body: Buffer.from(JSON.stringify(audit, null, 2)), contentType: 'application/json' });
    if (errors.length || failures.length) await info.attach('browser-errors.json', { body: Buffer.from(JSON.stringify({ errors, failures }, null, 2)), contentType: 'application/json' });
    if (info.status !== info.expectedStatus) {
      await info.attach('failure-dom.txt', { body: Buffer.from((await page.locator('body').innerText().catch(() => '')).slice(0, 70_000)), contentType: 'text/plain' });
      await page.screenshot({ path: info.outputPath('failure-masked.png'), fullPage: true, mask: [page.locator('input[type=password]')] }).catch(() => {});
    }
    if (errors.length && !info.title.includes('[injected]')) base.expect.soft(errors, 'Uncaught browser exceptions').toEqual([]);
    const unexpected = audit.filter(r => r.interception === 'blocked-unapproved-live-write');
    if (unexpected.length && !info.title.includes('[injected]')) base.expect.soft(unexpected, 'Test attempted an unregistered live write').toEqual([]);
  },
});
async function open(page, target) { await page.goto(target, { waitUntil: 'domcontentloaded' }); }
async function readyTable(page, name) { const t = page.getByRole('table', { name, exact: true }); await base.expect(t).toBeVisible(); await base.expect(t).toHaveAttribute('aria-busy', 'false'); return t; }
async function assertLayout(page) {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, document: document.documentElement.scrollWidth }));
  // A mobile browser may enlarge innerWidth to accommodate overflowing content.
  const limit = Math.min(dimensions.width, page.viewportSize()?.width || dimensions.width);
  base.expect(dimensions.document, `Document should fit the ${limit}px viewport; only the table may scroll internally`).toBeLessThanOrEqual(limit + 2);
}
async function checkA11y(page, testInfo) {
  const result = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']).analyze();
  const violations = result.violations.map(v => ({ id: v.id, impact: v.impact, description: v.description, help: v.help, helpUrl: v.helpUrl, nodes: v.nodes.map(n => ({ target: n.target, failureSummary: n.failureSummary })) }));
  await testInfo.attach('accessibility.json', { body: Buffer.from(JSON.stringify({ violations, passes: result.passes.length }, null, 2)), contentType: 'application/json' });
  base.expect.soft(violations.filter(v => ['serious', 'critical'].includes(v.impact)), 'Serious/critical WCAG violations').toEqual([]);
}
module.exports = { ...paths, test, expect: base.expect, open, readyTable, assertLayout, checkA11y, installGuard };
