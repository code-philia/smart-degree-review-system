import {beforeEach,afterEach,expect,it} from 'vitest';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const db=require('../src/database');
const {getDailyQuota,quotaAdmission}=require('../src/normative/paperLintQuota');
let harness;
beforeEach(async()=>{harness=db.createTestDatabaseHarness({label:'legacy-quota-compat'});await harness.setup();
await db.run("INSERT INTO auth_users(id,username,password_hash,role,scope) VALUES ('compat','compat','test','STUDENT','COLLEGE')");});
afterEach(async()=>await harness.cleanup());
it('keeps legacy quota readers compatible without a report-count limit',async()=>{
expect(await getDailyQuota('compat')).toMatchObject({limited:false,limit:0,used:0,reserved:0,remaining:null,resets_at:null});
await db.run("UPDATE paper_lint_credit_accounts SET spent_nano=granted_nano WHERE user_id='compat'");
expect(await getDailyQuota('compat')).toMatchObject({limited:false,remaining:null});
});
it('uses credit only for billable rules while rejecting absent users',async()=>{
const free=quotaAdmission('compat',null,['chinese_english_symbol_mix_check']);
const paid=quotaAdmission('compat',null,['typo_detection_check']);
expect((await db.get('SELECT ('+free.sql+') AS allowed',free.params)).allowed).toBe(1);
await db.run("UPDATE paper_lint_credit_accounts SET spent_nano=granted_nano WHERE user_id='compat'");
expect((await db.get('SELECT ('+paid.sql+') AS allowed',paid.params)).allowed).toBe(0);
await expect(getDailyQuota('missing')).rejects.toMatchObject({status:404});
});
