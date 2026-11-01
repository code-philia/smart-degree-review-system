import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const { runPaperLint } = require('../src/normative/reviewPilotPaperLintService');

it.skipIf(process.platform === 'win32')('delivers a semantic completion before the worker exits, without waiting for the slower rule', async () => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'lint-stream-test-'));
  const worker = path.join(directory, 'worker');
  const gate = path.join(directory, 'release');
  const ids = ['typo_detection_check', 'abstract_numeric_consistency_check'];
  const runs = ids.map(rule_id => ({ rule_id, rule_run_id: rule_id, execution_status: 'completed',
    severity: 'warning', outcome: 'passed', findings: [] }));
  await fs.writeFile(worker, `#!${process.execPath}
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
