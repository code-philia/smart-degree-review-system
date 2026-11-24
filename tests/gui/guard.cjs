const { run, created, record } = require('./paths.cjs');
const json = (route, body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
async function installGuard(context, { allowWrites = false, audit = [] } = {}) {
  await context.route('**/api/**', async route => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname, method = req.method();
    if (['GET', 'HEAD', 'OPTIONS'].includes(method)) return route.continue();
    if (/^\/api\/auth\/(?:supervision-login|trial-login|logout)$/.test(p)) return route.continue();
    if (p === '/api/auth/announcements/feedback/claim') { audit.push({ method, path: p, interception: 'preserve-account-announcement' }); return json(route, { announcement_id: 'gui-audit', show: false }); }
    if (/\/translations$/.test(p)) { audit.push({ method, path: p, interception: 'no-model-generation' }); return json(route, { locale: 'en', status: 'unavailable', translations: {}, source_hash: 'gui-audit' }); }
    if (/^\/api\/notifications\/read(?:-all)?$/.test(p)) return json(route, { success: true });
    if (/\/export$/.test(p) && method === 'POST') return route.continue(); // render-only export
    let body; try { body = req.postDataJSON(); } catch { body = null; }
    const marked = run().prefix, known = created();
    const reportIds = known.filter(r => r.kind === 'report').map(r => r.id);
    const jobIds = known.filter(r => r.kind === 'job').map(r => r.id);
    if (allowWrites && p === '/api/normative/paper-lint/run' && method === 'POST' && (url.searchParams.get('filename') || '').startsWith(marked)) {
      const selected = (req.headers()['x-paper-lint-rule-ids'] || '').split(',');
      const allowedFree = new Set(['required_section_completeness_check', 'keyword_count_check']);
      if (selected.length && selected.every(id => allowedFree.has(id))) {
        record({ kind: 'request', filename: url.searchParams.get('filename'), request_id: req.headers()['x-paper-lint-request-id'] });
        return route.continue();
      }
    }
    if (allowWrites && p === '/api/normative/feedback/system-feedback' && method === 'POST' && typeof body?.comment === 'string' && body.comment.startsWith(marked)) return route.continue();
    const reportId = p.match(/\/reports\/([^/]+)/)?.[1];
    if (allowWrites && reportIds.includes(reportId) && /\/feedback$/.test(p) && ['PUT', 'DELETE'].includes(method)) return route.continue();
    if (allowWrites && method === 'DELETE' && /^\/api\/normative\/paper-lint\/reports(?:\/[^/]+)?$/.test(p)) {
      const ids = reportId ? [reportId] : body?.report_ids;
      if (Array.isArray(ids) && ids.length && ids.every(id => reportIds.includes(id))) return route.continue();
    }
    const jobId = p.match(/\/jobs\/([^/]+)\/cancel$/)?.[1];
    if (allowWrites && jobIds.includes(jobId) && method === 'POST') return route.continue();
    audit.push({ method, path: p, interception: 'blocked-unapproved-live-write' });
    return json(route, { code: 409, message: 'GUI 测试保护：此写入未列入本次测试记录' }, 409);
  });
}
module.exports = { installGuard, json };
