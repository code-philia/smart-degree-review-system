import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import { afterAll, expect, it } from 'vitest';
const require=createRequire(import.meta.url);
const boundary=require('../src/normative/paperLintProcess');
const local=require('../src/normative/localFiveRulePaperLintService');
const originalAvailability=local.getLocalRuleAvailability;
local.getLocalRuleAvailability=async()=>true;
const original=boundary.runPaperLintProcess;
boundary.runPaperLintProcess=async (_python,args)=>{
  expect(args[0]).toMatch(/check_paper_document\.py$/);
  const required=['摘要','英文摘要','关键词','目录','引言','主体','结论','参考文献'];
  return {stdout:JSON.stringify({version:'paper-admission/2.0',status:'accepted',compiled:true,
    reason_code:'paper_structure_incomplete',stage:'partial',reason:'缺少目录',
    sha256:crypto.createHash('sha256').update(await fs.readFile(args[1])).digest('hex'),
    structure:{status:'rejected',profile:'chinese-thesis',required_sections:required,
      missing_sections:['目录'],incomplete_sections:[],
      observed_sections:Object.fromEntries(required.map(name=>[name,name!=='目录']))}})};
};
const names=['paperDocumentAdmission','reviewPilotPaperLintService'];
names.forEach(name=>delete require.cache[require.resolve(`../src/normative/${name}`)]);
const {runPaperLint}=require('../src/normative/reviewPilotPaperLintService');
afterAll(()=>{boundary.runPaperLintProcess=original;local.getLocalRuleAvailability=originalAvailability;names.forEach(name=>delete require.cache[require.resolve(`../src/normative/${name}`)]);});

it('never publishes a duplicate core alert before or after the dependency explanation',async()=>{
  const progress=[];
  const {result,selectedRuleIds}=await runPaperLint({pdfBuffer:Buffer.from('%PDF-progress'),
    selectedRuleIds:['sjtu_rule_28'],onProgress:async value=>progress.push(value)});
  expect(selectedRuleIds).toEqual(['sjtu_rule_28']);
  expect(progress.length).toBeGreaterThan(0);
  for(const snapshot of [...progress,result]){
    expect(snapshot.rule_runs.map(run=>run.rule_id)).toEqual(['sjtu_rule_28']);
    expect(snapshot.rule_runs[0]).toMatchObject({execution_status:'unsupported',outcome:'inconclusive'});
    expect(snapshot.rule_runs[0].message).toContain('缺少目录');
  }
});
