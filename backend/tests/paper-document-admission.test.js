import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const service = require('../src/normative/reviewPilotPaperLintService');

it.skipIf(process.platform === 'win32').each(['rejected', 'broken', 'crashed', 'stale', 'identity-only', 'truncated-proof', 'structure'])('blocks all detectors and records one severe document finding when admission is %s', async mode => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'paper-admission-test-'));
  const worker = path.join(directory, 'worker');
  const calls = path.join(directory, 'calls');
  await fs.writeFile(worker, `#!${process.execPath}
const fs=require('fs'),crypto=require('crypto');
const args=process.argv.slice(2);
fs.appendFileSync(${JSON.stringify(calls)},JSON.stringify(args)+'\\n');
if(args[0].endsWith('check_paper_document.py')) {
 if(${JSON.stringify(mode)}==='crashed') process.exit(2);
 if(${JSON.stringify(mode)}==='broken') { console.log('{}'); process.exit(0); }
 if(${JSON.stringify(mode)}==='truncated-proof') {
  console.log(JSON.stringify({version:'paper-admission/2.0',status:'accepted',reason_code:'paper_structure_confirmed',reason:'paper',compiled:true,stage:'complete',
   sha256:crypto.createHash('sha256').update(fs.readFileSync(args[1])).digest('hex'),
   structure:{status:'accepted',profile:'chinese-thesis',required_sections:['摘要'],observed_sections:{摘要:true},missing_sections:[]}}));process.exit(0);
 }
 console.log(JSON.stringify({version:'paper-admission/2.0',status:${JSON.stringify(mode)}==='identity-only'?'accepted':'rejected',
 reason_code:${JSON.stringify(mode)}==='structure'?'paper_structure_incomplete':${JSON.stringify(mode)}==='identity-only'?'paper_structure_confirmed':'non_paper_identity',
 reason:${JSON.stringify(mode)}==='structure'?'缺少必需章节：结论。':'推荐表不是论文。',
 sha256:${JSON.stringify(mode)}==='stale'?'0'.repeat(64):crypto.createHash('sha256').update(fs.readFileSync(args[1])).digest('hex')}));
} else if(args[0]==='-c') process.exit(0);
else { console.error('DETECTOR MUST NOT RUN');process.exit(9); }
`, { mode: 0o700 });
  const keys = ['PAPER_MODEL_PYTHON', 'FIVE_RULE_PYTHON', 'SJTU_API_KEY', 'SJTU_API_BASE_URL', 'SJTU_API_MODEL'];
  const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  Object.assign(process.env, { PAPER_MODEL_PYTHON: worker, FIVE_RULE_PYTHON: worker,
    SJTU_API_KEY: 'no-network', SJTU_API_BASE_URL: 'https://invalid.test', SJTU_API_MODEL: 'test' });
  try {
    const selectedRuleIds = ['sjtu_rule_18', 'abstract_numeric_consistency_check'];
    const snapshots = [];
    const checked = await service.runPaperLint({ pdfBuffer: Buffer.from('%PDF-test'), selectedRuleIds,
      externalProcessingConsent: true, onProgress: async progress => snapshots.push(progress) });
    expect(checked.result.document_validation.status).toBe('rejected');
    expect(checked.result.rule_runs).toHaveLength(1);
    expect(checked.result.rule_runs[0]).toMatchObject({ rule_id: 'document_type_check', severity: 'error',
      outcome: 'issues_found', execution_status: 'completed', findings: [expect.objectContaining({ severity: 'error' })] });
    expect(checked.result.summary).toMatchObject({ finding_count: 1, error_finding_count: 1, rule_count: 0, completed_rule_count: 0 });
    if (mode === 'structure') expect(checked.result.rule_runs[0].findings[0].message).toContain('论文核心章节不完整，Paper Model 编译失败');
    if (mode === 'rejected') expect(checked.result.document_validation.reason_code).toBe('non_paper_identity');
    expect(snapshots.at(-1).rule_runs.map(run => run.rule_id)).toEqual(['document_type_check']);
    const invoked = (await fs.readFile(calls, 'utf8')).trim().split('\n').map(row => JSON.parse(row));
    expect(invoked.filter(args => args[0] !== '-c')).toEqual([[expect.stringContaining('check_paper_document.py'), expect.any(String)]]);
  } finally {
    for (const [key, value] of Object.entries(previous)) { if (value === undefined) delete process.env[key]; else process.env[key] = value; }
    await fs.rm(directory, { recursive: true, force: true });
  }
});
