import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const { createArchiveScanService } = require('../src/normative/archiveScanService');
const harness = createTestDatabaseHarness({ label: 'archive-rule-counts' });
let db, service;
function rule(number, count, outcome = count ? 'issues_found' : 'passed') {
  const rule_id = 'sjtu_rule_' + number;
  return { rule_id, outcome, findings: Array.from({ length: count }, (_, i) => ({
    finding_id: rule_id + '_' + i, rule_id, message: 'issue ' + i,
  })) };
}
async function save(id, runs, count) {
  await db.run('INSERT INTO archive_scan_documents (id,job_id,relative_path,filename,size_bytes,status,finding_count,rule_outcomes_json,result_json) VALUES (?,?,?,?,?,?,?,?,?)',
    [id,'job',id+'.pdf',id+'.pdf',100,'completed',count,
      JSON.stringify(Object.fromEntries(runs.map(r => [r.rule_id,r.outcome]))),
      JSON.stringify({rule_runs:runs,summary:{finding_count:count}})]);
}
beforeEach(async () => {
  db = await harness.setup();
  await db.run("INSERT INTO auth_users (id,username,password_hash,role,scope) VALUES ('admin','countadmin','hash','SCHOOL_ADMIN','SCHOOL')");
  await db.run("INSERT INTO archive_scan_jobs (id,created_by,selected_rule_ids_json,status,total_count) VALUES ('job','admin',?,'completed',26)",
    [JSON.stringify(['sjtu_rule_11','sjtu_rule_14','sjtu_rule_15'])]);
  service = createArchiveScanService();
});
afterEach(async () => { await harness.cleanup(); });
describe('archive rule-scoped finding counts', () => {
  it('counts the selected rule and preserves the full stored report', async () => {
    await save('a',[rule(11,1),rule(14,0),rule(15,4)],5);
    await save('b',[rule(11,2),rule(14,0),rule(15,3)],5);
    const eleven=await service.listDocuments('job',{ruleId:'sjtu_rule_11',outcome:'issues_found'});
    expect(eleven.items.map(d=>d.finding_count)).toEqual([1,2]);
    expect(eleven.finding_count).toBe(3);
    expect(eleven.items[0]).not.toHaveProperty('result_json');
    const fifteen=await service.listDocuments('job',{ruleId:'sjtu_rule_15'});
    expect(fifteen.items.map(d=>d.finding_count)).toEqual([4,3]);
    expect(fifteen.finding_count).toBe(7);
    const all=await service.listDocuments('job');
    expect(all.items.map(d=>d.finding_count)).toEqual([5,5]);
    expect(all.finding_count).toBe(10);
    const detail=await service.getDocument('job','a');
    expect(detail.finding_count).toBe(5);
    expect(detail.result.rule_runs[2].findings).toHaveLength(4);
  });
  it('does not count other rule violations for passed, inconclusive, or searched results', async () => {
    await save('a',[rule(11,1),rule(14,0,'inconclusive'),rule(15,0)],1);
    await save('b',[rule(11,0),rule(14,0),rule(15,4)],4);
    const passed=await service.listDocuments('job',{ruleId:'sjtu_rule_11',outcome:'passed'});
    expect(passed.items.map(d=>[d.id,d.finding_count])).toEqual([['b',0]]);
    expect(passed.finding_count).toBe(0);
    const unknown=await service.listDocuments('job',{ruleId:'sjtu_rule_14',outcome:'inconclusive'});
    expect(unknown.items.map(d=>[d.id,d.finding_count])).toEqual([['a',0]]);
    expect(unknown.finding_count).toBe(0);
    const search=await service.listDocuments('job',{ruleId:'sjtu_rule_11',query:'a.pdf'});
    expect(search.finding_count).toBe(1);
    const empty=await service.listDocuments('job',{ruleId:'sjtu_rule_99'});
    expect(empty.items).toEqual([]);
    expect(empty.finding_count).toBe(0);
  });
  it('sums all matching documents before pagination', async () => {
    for(let i=0;i<26;i++) await save('paper-'+String(i).padStart(2,'0'),[rule(11,1),rule(15,2)],3);
    const first=await service.listDocuments('job',{ruleId:'sjtu_rule_11'});
    expect(first.total).toBe(26);
    expect(first.items).toHaveLength(25);
    expect(first.finding_count).toBe(26);
    const last=await service.listDocuments('job',{ruleId:'sjtu_rule_11',page:2});
    expect(last.items.map(d=>d.finding_count)).toEqual([1]);
    expect(last.finding_count).toBe(26);
  });
});
