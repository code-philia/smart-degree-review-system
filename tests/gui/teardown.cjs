const { request } = require('@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const { OUT, BASE, state, created, record, run } = require('./paths.cjs');
module.exports = async () => {
  if (!fs.existsSync(state('student'))) return;
  const api = await request.newContext({ baseURL: BASE, storageState: state('student'), extraHTTPHeaders: { Origin: BASE } });
  const cleanup = { reports: [], jobs: [], systemFeedback: [], errors: [] };
  try {
    for (const job of created().filter(r => r.kind === 'job')) {
      const response = await api.get('/api/normative/paper-lint/jobs/' + encodeURIComponent(job.id));
      if (!response.ok()) continue;
      const current = await response.json();
      if (!current.source_filename?.startsWith(run().prefix) || current.user_id !== 'student01') throw new Error('Cleanup refused mismatched job');
      if (['pending', 'running'].includes(current.status)) await api.post('/api/normative/paper-lint/jobs/' + encodeURIComponent(job.id) + '/cancel', { data: {} });
      if (current.report_id) record({ kind: 'report', id: current.report_id, filename: current.source_filename, job_id: job.id });
      cleanup.jobs.push({ id: job.id, status: current.status, server_cleanup_required: true });
    }
    for (const id of [...new Set(created().filter(r => r.kind === 'report').map(r => r.id))]) {
      const url = '/api/normative/paper-lint/reports/' + encodeURIComponent(id);
      const response = await api.get(url, { timeout: 40_000 });
      if (response.status() === 404) { cleanup.reports.push({ id, already_removed_in_gui: true }); continue; }
      if (!response.ok()) { cleanup.errors.push({ id, status: response.status() }); continue; }
      const report = await response.json();
      if (report.id !== id || !report.source_filename?.startsWith(run().prefix)) throw new Error('Cleanup refused non-test report');
      const deletion = await api.delete(url);
      if (!deletion.ok()) cleanup.errors.push({ id, status: deletion.status() });
      else cleanup.reports.push({ id, removed: true });
    }
    cleanup.systemFeedback = created().filter(r => r.kind === 'system-feedback').map(r => ({ id: r.id, server_cleanup_required: true }));
  } finally { await api.dispose(); fs.writeFileSync(path.join(OUT, 'api-cleanup.json'), JSON.stringify(cleanup, null, 2)); }
  if (cleanup.errors.length) throw new Error('Test-created report cleanup incomplete; inspect api-cleanup.json');
};
