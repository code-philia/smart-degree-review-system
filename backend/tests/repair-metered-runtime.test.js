import { afterEach, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const service = require('../src/normative/repairModelProposalService');
const original = process.env.REPAIR_MODEL_PYTHON;
let root;
afterEach(() => {
  if (original === undefined) delete process.env.REPAIR_MODEL_PYTHON;
  else process.env.REPAIR_MODEL_PYTHON = original;
  if (root) fs.rmSync(root, { recursive: true, force: true });
});
const request = { source: {}, rule: {rule_id:'sjtu_rule_15',text:'图应随文出现'},
  finding:{finding_id:'f1',message:'缺少引用'}, context_sha256:'hash',
  evidence:[{evidence_id:'e1',text:'图1',source_kind:'pdf_text'}] };
it('uses the metered Python runtime and existing credential configuration by default', async () => {
  root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-metered-'));
  const capture=path.join(root,'input.json');const shim=path.join(root,'python');
  const payload={answer:{status:'suggested',actions:[{instruction:'核对后补充正文引用',evidence_ids:['e1']}]},
    model:'metered-model',modelVersion:'v1',usage:{input_tokens:20,output_tokens:10,attempts:1}};
  fs.writeFileSync(shim,`#!${process.execPath}\nlet data='';process.stdin.on('data',x=>data+=x);process.stdin.on('end',()=>{require('fs').writeFileSync(${JSON.stringify(capture)},data);process.stdout.write(${JSON.stringify(JSON.stringify(payload))});});\n`,{mode:0o700});
  process.env.REPAIR_MODEL_PYTHON=shim;
  const result=await service.proposeRepair(request);
  expect(result.status).toBe('suggested');expect(result.provenance.model).toBe('metered-model');
  expect(result.usage.input_tokens).toBe(20);
  expect(JSON.parse(fs.readFileSync(capture,'utf8')).messages[0].role).toBe('system');
});
it('preserves a structured budget stop instead of retrying another transport', async () => {
  root=fs.mkdtempSync(path.join(os.tmpdir(),'repair-budget-'));const shim=path.join(root,'python');
  fs.writeFileSync(shim,`#!${process.execPath}\nprocess.stdin.resume();process.stdin.on('end',()=>{process.stdout.write(JSON.stringify({status:'error',http_status:429,message:'修复建议预算已用尽'}));process.exitCode=1;});\n`,{mode:0o700});
  process.env.REPAIR_MODEL_PYTHON=shim;
  await expect(service.proposeRepair(request)).rejects.toMatchObject({status:429});
});
