import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const { runPaperLint } = require('../src/normative/reviewPilotPaperLintService');
const admissionStub = `
if (process.argv[2]?.endsWith('check_paper_document.py')) {
  const fs=require('fs'),crypto=require('crypto');
  console.log(JSON.stringify({version:'paper-admission/2.0',status:'accepted',reason_code:'paper_structure_confirmed',reason:'test paper',compiled:true,stage:'complete',structure:{status:'accepted',profile:'research-article',required_sections:['摘要','引言','主体','结论','参考文献'],observed_sections:{'摘要':true,'引言':true,'主体':true,'结论':true,'参考文献':true},missing_sections:[],incomplete_sections:[]},
    sha256:crypto.createHash('sha256').update(fs.readFileSync(process.argv[3])).digest('hex')}));
  process.exit(0);
}
`;


it.skipIf(process.platform === 'win32')('delivers a semantic completion before the worker exits, without waiting for the slower rule', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'lint-stream-test-'));
  const worker = path.join(directory, 'worker');
  const gate = path.join(directory, 'release');
  const ids = ['typo_detection_check', 'abstract_numeric_consistency_check'];
  const runs = ids.map(rule_id => ({ rule_id, rule_run_id: rule_id, execution_status: 'completed',
    severity: 'warning', outcome: 'passed', findings: [] }));
  await fs.writeFile(worker, `#!${process.execPath}
${admissionStub}
const fs = require('fs');
const runs = ${JSON.stringify(runs)};
console.log(JSON.stringify({type:'paper_lint_rule_complete',rule_run:runs[1]}));
const timer=setInterval(()=>{
  if (!fs.existsSync(${JSON.stringify(gate)})) return;
  clearInterval(timer);
  console.log(JSON.stringify({type:'paper_lint_rule_complete',rule_run:runs[0]}));
  console.log(JSON.stringify({type:'paper_lint',rule_runs:runs,summary:{}}));
},10);
`, { mode: 0o700 });
  const previous = Object.fromEntries(['PAPER_MODEL_PYTHON', 'SJTU_API_KEY', 'SJTU_API_BASE_URL', 'SJTU_API_MODEL'].map(key => [key, process.env[key]]));
  Object.assign(process.env, { PAPER_MODEL_PYTHON: worker, SJTU_API_KEY: 'unit-test-no-network',
    SJTU_API_BASE_URL: 'https://invalid.test', SJTU_API_MODEL: 'test' });
  const controller = new AbortController();
  let execution;
  try {
    let notify;
    const first = new Promise(resolve => { notify = resolve; });
    const snapshots = [];
    let settled = false;
    execution = runPaperLint({ pdfBuffer: Buffer.from('%PDF-test'), selectedRuleIds: ids,
      externalProcessingConsent: true, background: true, signal: controller.signal,
      onProgress: async snapshot => { snapshots.push(snapshot); notify(); },
    }).finally(() => { settled = true; });
    await Promise.race([first, execution]);
    expect(snapshots.map(snapshot => snapshot.completed_rule_ids)).toEqual([[ids[1]]]);
    expect(settled).toBe(false);
    await fs.writeFile(gate, 'go');
    const result = await execution;
    expect(result.result.rule_runs.map(run => run.rule_id)).toEqual(ids);
    expect(snapshots.map(snapshot => snapshot.completed_rule_ids)).toEqual([[ids[1]], [ids[1], ids[0]]]);
  } finally {
    controller.abort();
    await execution?.catch(() => {});
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
    await fs.rm(directory, { recursive: true, force: true });
  }
});


it.skipIf(process.platform === 'win32')('keeps published results and reports only unfinished rules as errors when a semantic worker exits', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'lint-partial-failure-'));
  const worker = path.join(directory, 'worker');
  const ids = ['typo_detection_check', 'bilingual_keywords_correspondence_check', 'bilingual_abstract_consistency_check'];
  const completed = { rule_id: ids[0], rule_run_id: 'finished', execution_status: 'completed',
    severity: 'warning', outcome: 'issues_found', findings: [{ finding_id: 'kept', rule_id: ids[0], message: '保留已完成的问题' }] };
  await fs.writeFile(worker, `#!${process.execPath}
${admissionStub}
console.log(JSON.stringify({type:'paper_lint_rule_complete',rule_run:${JSON.stringify(completed)}}));
console.log(JSON.stringify({error:'simulated semantic worker failure'}));
process.exitCode=1;
`, { mode: 0o700 });
  const keys = ['PAPER_MODEL_PYTHON','SJTU_API_KEY','SJTU_API_BASE_URL','SJTU_API_MODEL'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  Object.assign(process.env, { PAPER_MODEL_PYTHON: worker, SJTU_API_KEY: 'unit-test-no-network',
    SJTU_API_BASE_URL: 'https://invalid.test', SJTU_API_MODEL: 'test' });
  try {
    const snapshots = [];
    const checked = await runPaperLint({ pdfBuffer: Buffer.from('%PDF-test'), selectedRuleIds: ids,
      externalProcessingConsent: true, background: true, onProgress: async progress => snapshots.push(progress) });
    expect(checked.result.rule_runs.map(run => run.rule_id)).toEqual(ids);
    expect(checked.result.rule_runs[0]).toEqual(completed);
    expect(checked.result.rule_runs.slice(1).map(run => run.execution_status)).toEqual(['error','error']);
    expect(checked.result.summary.finding_count).toBe(1);
    expect(checked.result.summary.error_rule_count).toBe(2);
    expect(snapshots.at(-1).completed_rule_ids).toHaveLength(3);
  } finally {
    for (const [key,value] of Object.entries(previous)) { if (value === undefined) delete process.env[key]; else process.env[key]=value; }
    await fs.rm(directory, { recursive: true, force: true });
  }
});


it.skipIf(process.platform === 'win32')('still propagates user cancellation instead of saving a partial success', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'lint-cancel-'));
  const worker = path.join(directory, 'worker');
  const id = 'typo_detection_check';
  await fs.writeFile(worker, `#!${process.execPath}
${admissionStub}
console.log(JSON.stringify({type:'paper_lint_rule_complete',rule_run:{rule_id:'${id}',execution_status:'completed',outcome:'passed',findings:[]}}));
setInterval(()=>{},1000);
`, { mode: 0o700 });
  const keys = ['PAPER_MODEL_PYTHON','SJTU_API_KEY','SJTU_API_BASE_URL','SJTU_API_MODEL'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  Object.assign(process.env, { PAPER_MODEL_PYTHON: worker, SJTU_API_KEY: 'unit-test-no-network',
    SJTU_API_BASE_URL: 'https://invalid.test', SJTU_API_MODEL: 'test' });
  const controller = new AbortController();
  try {
    await expect(runPaperLint({ pdfBuffer: Buffer.from('%PDF-test'), selectedRuleIds: [id],
      externalProcessingConsent: true, background: true, signal: controller.signal,
      onProgress: async () => controller.abort(),
    })).rejects.toMatchObject({ code: 'PAPER_LINT_CANCELLED' });
  } finally {
    controller.abort();
    for (const [key,value] of Object.entries(previous)) { if (value === undefined) delete process.env[key]; else process.env[key]=value; }
    await fs.rm(directory, { recursive: true, force: true });
  }
});
