import {afterEach,expect,it,vi} from 'vitest';
import {createRequire} from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
const require=createRequire(import.meta.url);
const core=require('../src/normative/referenceVerificationCore');
const service=require('../src/normative/reviewPilotPaperLintService');
const settings=require('../src/auth/referenceSettingsService');
const pdf=path.resolve('..','output/reference-verification-20261125/archived-zh.pdf');
afterEach(()=>vi.restoreAllMocks());
it.skipIf(!fs.existsSync(pdf))('routes a real archived native PDF through the new rule runner without executing model or retired rules',async()=>{
  const seen=[];
  vi.spyOn(settings,'getReferenceCredentials').mockResolvedValue({personalKey:'fixture-owned-openalex'});
  vi.spyOn(core,'verifyReference').mockImplementation(async entry=>{
    seen.push(entry);
    return {category:'verified',reason_code:'identifier_verified',matched:{title:entry.title},sources:[],comparisons:[],coverage:{complete:true}};
  });
  const checked=await service.runPaperLint({userId:'fixture:reference-flow',pdfBuffer:fs.readFileSync(pdf),selectedRuleIds:['reference_verification_check'],onProgress:async()=>{}});
  const run=checked.result.rule_runs.find(r=>r.rule_id==='reference_verification_check');
  expect(seen).toHaveLength(67);
  expect(run.findings).toEqual([]);
  expect(run.params.reference_verification.entries).toHaveLength(67);
  expect(checked.result.rule_runs.some(r=>r.rule_id==='sjtu_rule_32')).toBe(false);
},30000);
