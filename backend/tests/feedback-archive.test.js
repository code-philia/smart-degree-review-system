import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
const require = createRequire(import.meta.url);
const { createTestDatabaseHarness } = require('../src/database/test_harness');
const feedback = require('../src/normative/paperLintFeedbackService');
const reports = require('../src/normative/paperLintReportRepository');
let root, harness, db, dir;
beforeEach(async () => {
  root = await fs.mkdtemp(path.join(os.tmpdir(), 'feedback-archive-test-'));
  harness = createTestDatabaseHarness({ dbPath: path.join(root, 'test.db') });
  db = await harness.setup();
  dir = path.join(root, 'feedback');
  await db.run("INSERT INTO auth_users (id,username,display_name,password_hash,role,scope) VALUES ('owner','student','学生','DO_NOT_EXPORT_PASSWORD','STUDENT','COLLEGE')");
  await reports.createPaperLintReport({ userId: 'owner', sourceFilename: '论文.pdf', pdfBuffer: Buffer.from('%PDF-1.7'), selectedRuleIds: ['sjtu_rule_15'], reportId: 'report-1', result: { rule_runs: [{ rule_id: 'sjtu_rule_15', findings: [{ finding_id: 'finding-15-1', message: 'DO_NOT_EXPORT_THESIS_BODY', location: { page_number: 1 } }] }] } });
});
afterEach(async () => {
  vi.restoreAllMocks();
  await harness.cleanup();
  await fs.rm(root, { recursive: true, force: true });
});
const read = async () => JSON.parse(await fs.readFile(path.join(dir, 'feedback.json'), 'utf8'));
describe('private backend feedback snapshots', () => {
  it('automatically archives successful system feedback with identity and time, without secrets or thesis body', async () => {
    await feedback.saveSystemFeedback({ userId: 'owner', input: { satisfaction_score: 4, improvement_areas: ['system_response_speed'], comment: '建议', request_id: 'once' } });
    expect(await fs.stat(path.join(dir, 'feedback.json')).then(() => true, () => false)).toBe(true);
    const result = await read();
    expect(result.records).toHaveLength(1);
    expect(result.records[0]).toMatchObject({ type: 'system', username: 'student', user_id: 'owner', display_name: '学生', satisfaction_score: 4, comment: '建议', improvement_areas: ['system_response_speed'] });
    expect(result.records[0].created_at).toBeTruthy();
    expect(JSON.stringify(result)).not.toMatch(/DO_NOT_EXPORT/);
    expect(await fs.readFile(path.join(dir, 'feedback.csv'), 'utf8')).toContain('建议');
    expect((await fs.stat(dir)).mode & 0o077).toBe(0);
    expect((await fs.stat(path.join(dir, 'feedback.csv'))).mode & 0o077).toBe(0);
  });
  it('reflects a finding vote, updated reason and withdrawal without duplicates', async () => {
    const target = { reportId: 'report-1', userId: 'owner', ruleId: 'sjtu_rule_15', findingId: 'finding-15-1' };
    await feedback.saveFindingFeedback({ ...target, input: { feedback_value: 'negative', reason_code: 'false_positive', reason_text: '误报说明' } });
    expect((await read()).records[0]).toMatchObject({ type: 'finding', source_filename: '论文.pdf', feedback_value: 'negative', reason_code: 'false_positive', reason_text: '误报说明' });
    await feedback.saveFindingFeedback({ ...target, input: { feedback_value: 'positive' } });
    expect((await read()).records).toHaveLength(1);
    expect((await read()).records[0]).toMatchObject({ feedback_value: 'positive', reason_code: null, reason_text: null });
    await feedback.deleteFindingFeedback(target);
    expect((await read()).records).toEqual([]);
  });
  it('exports all three kinds, preserves raw JSON and neutralises spreadsheet formulas', async () => {
    await db.run("INSERT INTO system_feedback (id,user_id,satisfaction_score,comment,created_at) VALUES ('a','owner',3,?, '2026-11-12 00:00:00')", [' =HYPERLINK("bad")\n下一行']);
    await db.run("INSERT INTO paper_lint_finding_feedback (id,user_id,report_id,rule_id,finding_id,feedback_value) VALUES ('b','owner','report-1','sjtu_rule_15','finding-15-1','positive')");
    // Existing suggestions can be seeded; no model is called.
    const { report, ruleRun, finding } = await require('../src/normative/paperLintRepairSuggestionService').getPaperLintReportFinding({ reportId:'report-1', userId:'owner', ruleId:'sjtu_rule_15', findingId:'finding-15-1' });
    const repair = require('../src/normative/legacyRepairAdapter').buildPaperLintReportRepairRequest({ report, ruleRun, finding, documentSha256:'hash' });
    const answer = { schema_version:'repair-response-v2', source:repair.source, rule_id:'sjtu_rule_15', finding_id:finding.finding_id, status:'suggested', actions:[], provenance:{ provider:'huawei_maas', model:'test', model_version:'v1', prompt_version:'p1', context_sha256:repair.context_sha256 }, usage:{} };
    const suggestion = await require('../src/normative/paperLintRepairSuggestionService').savePaperLintRepairSuggestion(repair,'owner',answer);
    await feedback.saveSuggestionFeedback({ reportId:'report-1', userId:'owner', suggestionId:suggestion.suggestion_id, input:{ feedback_value:'negative', reason_code:'unclear', reason_text:'说明不清楚' } });
    const result = await read();
    expect(result.records.map(r=>r.type).sort()).toEqual(['finding','suggestion','system']);
    expect(result.records.find(r=>r.type==='suggestion')).toMatchObject({ suggestion_id:suggestion.suggestion_id, generation:1, reason_code:'unclear' });
    expect(result.records.find(r=>r.type==='system').comment).toBe(' =HYPERLINK("bad")\n下一行');
    const csv = await fs.readFile(path.join(dir,'feedback.csv'),'utf8');
    expect(csv.startsWith('\uFEFF')).toBe(true);
    expect(csv).toContain("' =HYPERLINK");
    expect(csv).toContain('2026-11-12 08:00:00');
    expect(JSON.stringify(result)).not.toMatch(/DO_NOT_EXPORT/);
  });
  it('serialises concurrent refreshes and can rebuild an existing database without duplicate rows', async () => {
    await Promise.all(Array.from({ length:6 }, (_,i)=>feedback.saveSystemFeedback({ userId:'owner', input:{ satisfaction_score:5, request_id:'id-'+i } })));
    const archive = require('../src/normative/feedbackArchive');
    await Promise.all([archive.refreshFeedbackArchive(),archive.refreshFeedbackArchive()]);
    expect((await read()).records).toHaveLength(6);
    expect((await fs.readdir(dir)).sort()).toEqual(['feedback.csv','feedback.json']);
  });
  it('keeps valid feedback when archive writes fail, and supports later rebuilding', async () => {
    await fs.writeFile(dir,'blocked');
    const log = vi.spyOn(console,'error').mockImplementation(()=>{});
    await expect(feedback.saveSystemFeedback({userId:'owner',input:{satisfaction_score:4,comment:'已保存'}})).resolves.toMatchObject({duplicate:false});
    expect((await db.all('SELECT id FROM system_feedback')).length).toBe(1);
    expect(log).toHaveBeenCalled();
    await fs.unlink(dir);
    await require('../src/normative/feedbackArchive').refreshFeedbackArchive();
    expect((await read()).records[0].comment).toBe('已保存');
  });
  it('does not create archives for rejected feedback', async () => {
    await expect(feedback.saveSystemFeedback({userId:'owner',input:{satisfaction_score:9}})).rejects.toMatchObject({status:400});
    expect(await fs.stat(dir).then(()=>true,()=>false)).toBe(false);
  });
});

it.each(['single','batch'])('removes cascaded feedback when a report is deleted (%s)',async(kind)=>{
 const target={reportId:'report-1',userId:'owner',ruleId:'sjtu_rule_15',findingId:'finding-15-1'};
 await feedback.saveFindingFeedback({...target,input:{feedback_value:'negative',reason_code:'false_positive'}});
 expect((await read()).records).toHaveLength(1);
 if(kind==='single')await reports.deletePaperLintReportForUser('report-1','owner');
 else await reports.deletePaperLintReportsForUser(['report-1'],'owner');
 expect((await read()).records).toEqual([]);
});
