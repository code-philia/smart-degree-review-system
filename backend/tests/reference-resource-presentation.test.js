import { createRequire } from 'node:module';
import { expect, it } from 'vitest';
import { referenceInfoFindings, displayedReportSummary, referenceResourcesUnavailable } from '../../shared/paper-lint-presentation.mjs';
const require = createRequire(import.meta.url);
const repository = require('../src/normative/paperLintReportRepository');
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const harness = createTestDatabaseHarness({ label: 'reference-resource-presentation' });
const id = 'sjtu_rule_32';
function mixed(reason) {
  return { rule_id: id, execution_status: 'completed', outcome: 'inconclusive', severity: 'info',
    message: '检索资源暂不可用：部分参考文献未完成核验。',
    findings: [
      { finding_id: 'suspect', prompt_only: true, reference_review: 'supported_suspicion' },
      { finding_id: 'reference-info-blocked-existence-0', prompt_only: true, reference_review: 'insufficient_evidence' },
    ],
    compiler_diagnostics: [
      { node_id: 'blocked', check_id: 'existence', status: 'UNKNOWN', reasons: [reason] },
      { node_id: 'searched', check_id: 'existence', status: 'UNKNOWN', reasons: ['reference_not_matched'] },
    ] };
}
it.each(['SERPAPI_QUOTA_EXHAUSTED', 'SERPAPI_API_KEY is not configured', 'reference_lookup_unavailable: HTTP_429', 'TimeoutError'])(
  'excludes resource-blocked notices from blue results while retaining actual search outcomes: %s', reason => {
    const run = mixed(reason);
    expect(referenceResourcesUnavailable({ ...run, message: null })).toBe(true);
    const findings = referenceInfoFindings(run);
    expect(findings.map(f => f.finding_id)).toEqual(['suspect', 'reference-info-searched-existence-1']);
    expect(referenceInfoFindings({ ...run, findings })).toEqual(findings);
    expect(displayedReportSummary({ rule_runs: [run] })).toMatchObject({ finding_count: 3, info_finding_count: 2, execution_warning_count: 1 });
  });
it('keeps supported suspicions when older records mark all unresolved entries unavailable', () => {
  const run = { ...mixed('SERPAPI_QUOTA_EXHAUSTED'), compiler_diagnostics: [],
    params: { reference_verification: { unresolved: 1, unavailable: 1 } } };
  expect(referenceInfoFindings(run).map(f => f.finding_id)).toEqual(['suspect']);
});
it.each([false, true])('aligns saved detail and history counts without rewriting original report JSON (legacy=%s)', async legacy => {
  try {
    const db = await harness.setup();
    await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES('owner','owner','hash','STUDENT','COLLEGE')");
    const run = mixed('SERPAPI_QUOTA_EXHAUSTED');
    if (legacy) run.message = '未触发告警';
    const result = { rule_runs: [run], summary: { finding_count: 99 } };
    const original = JSON.stringify(result);
    await db.run('INSERT INTO paper_lint_reports(id,user_id,source_filename,source_pdf_path,selected_rule_ids_json,result_json,created_at) VALUES(?,?,?,?,?,?,?)',
      ['saved', 'owner', 'saved.pdf', 'unused.pdf', '["sjtu_rule_32"]', original, new Date().toISOString()]);
    const [history] = await repository.listPaperLintReportsByUser('owner');
    const detail = await repository.findPaperLintReportByIdForUser('saved', 'owner');
    expect(history.summary).toMatchObject({ finding_count: 3, info_finding_count: 2, execution_warning_count: 1 });
    expect(detail.summary).toEqual(history.summary);
    if (legacy) expect(detail.result.rule_runs[0].message).toContain('额度');
    else expect(detail.result.rule_runs[0].message).toBe(run.message);
    expect((await db.get('SELECT result_json FROM paper_lint_reports WHERE id=?', ['saved'])).result_json).toBe(original);
  } finally { await harness.cleanup(); }
});
