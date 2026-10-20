import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const harness = createTestDatabaseHarness({ label: 'dismiss-archive-finding' });
let db, review, original;
beforeEach(async () => {
  db = await harness.setup();
  await db.run("INSERT INTO auth_users (id,username,password_hash,role,scope) VALUES ('admin','reviewadmin','hash','SCHOOL_ADMIN','SCHOOL')");
  await db.run("INSERT INTO archive_scan_jobs (id,created_by,selected_rule_ids_json,status,total_count,completed_count,finding_count) VALUES ('job','admin','[\"sjtu_rule_22\",\"sjtu_rule_24\"]','completed',2,2,3)");
  original = JSON.stringify({
    type: 'paper_lint',
    rule_runs: [{
      rule_id: 'sjtu_rule_22', execution_status: 'completed', severity: 'warning', outcome: 'issues_found',
      findings: [{ rule_id: 'sjtu_rule_22', finding_id: 'same-id', message: 'confirmed false alarm', location: {type:'pdf_page',page_number:31} }],
    }, {
      rule_id: 'sjtu_rule_24', execution_status: 'completed', severity: 'warning', outcome: 'issues_found',
      findings: [{ rule_id: 'sjtu_rule_24', finding_id: 'keep', message: 'keep this issue' }],
    }],
    summary: { rule_count: 2, completed_rule_count: 2, issue_rule_count: 2, finding_count: 2, warning_finding_count: 2, error_finding_count: 0, info_finding_count: 0 },
  });
  for (const [id, count] of [['target',2],['other',1]]) {
    await db.run('INSERT INTO archive_scan_documents (id,job_id,relative_path,filename,size_bytes,status,finding_count,rule_outcomes_json,result_json) VALUES (?,?,?,?,?,?,?,?,?)',
      [id,'job',id+'.pdf',id+'.pdf',100,'completed',count,JSON.stringify({sjtu_rule_22:'issues_found',sjtu_rule_24:'issues_found'}), id==='target' ? original : JSON.stringify({rule_runs:[{rule_id:'sjtu_rule_22',findings:[{finding_id:'same-id',message:'different paper'}]}],summary:{finding_count:1}})]);
  }
  review = { jobId:'job', documentId:'target', ruleId:'sjtu_rule_22', findingId:'same-id',
    expectedResultSha256:createHash('sha256').update(original).digest('hex'), reason:'用户确认这条报警是误报' };
});
afterEach(async () => { await harness.cleanup(); });
async function dismiss(input = review) {
  return require('../scripts/dismissArchiveFinding').dismissArchiveFinding(input);
}
describe('confirmed archive false-positive removal', () => {
  it('removes only the selected finding, retains its audit record, and synchronizes counts', async () => {
    const other = await db.get("SELECT * FROM archive_scan_documents WHERE id='other'");
    expect((await dismiss()).changed).toBe(true);
    const row = await db.get("SELECT * FROM archive_scan_documents WHERE id='target'");
    const result = JSON.parse(row.result_json);
    expect(result.rule_runs[0].findings).toEqual([]);
    expect(result.rule_runs[0].outcome).toBe('passed');
    expect(result.rule_runs[1].findings[0].message).toBe('keep this issue');
    expect(result.summary).toMatchObject({rule_count:2,completed_rule_count:2,issue_rule_count:1,finding_count:1,warning_finding_count:1,error_finding_count:0,info_finding_count:0});
    expect(result.finding_reviews[0]).toMatchObject({rule_id:'sjtu_rule_22',finding_id:'same-id',disposition:'false_positive',reason:review.reason,original_finding:JSON.parse(original).rule_runs[0].findings[0]});
    expect(row.finding_count).toBe(1);
    expect(JSON.parse(row.rule_outcomes_json)).toEqual({sjtu_rule_22:'passed',sjtu_rule_24:'issues_found'});
    expect((await db.get("SELECT finding_count FROM archive_scan_jobs WHERE id='job'")).finding_count).toBe(2);
    expect(await db.get("SELECT * FROM archive_scan_documents WHERE id='other'")).toEqual(other);
  });
  it('is idempotent and does not decrement counts twice', async () => {
    await dismiss();
    const row = await db.get("SELECT * FROM archive_scan_documents WHERE id='target'");
    expect((await dismiss()).changed).toBe(false);
    expect(await db.get("SELECT * FROM archive_scan_documents WHERE id='target'")).toEqual(row);
    expect((await db.get("SELECT finding_count FROM archive_scan_jobs WHERE id='job'")).finding_count).toBe(2);
  });
  it('rejects a stale source fingerprint before any write', async () => {
    await expect(dismiss({...review,expectedResultSha256:'0'.repeat(64)})).rejects.toThrow(/changed/);
    expect((await db.get("SELECT result_json FROM archive_scan_documents WHERE id='target'")).result_json).toBe(original);
    expect((await db.get("SELECT finding_count FROM archive_scan_jobs WHERE id='job'")).finding_count).toBe(3);
  });
  it('does not remove a different finding or a record belonging to another job', async () => {
    await expect(dismiss({...review,findingId:'missing'})).rejects.toThrow(/finding/);
    await expect(dismiss({...review,jobId:'different'})).rejects.toThrow(/document/);
    expect((await db.get("SELECT result_json FROM archive_scan_documents WHERE id='target'")).result_json).toBe(original);
  });
});
