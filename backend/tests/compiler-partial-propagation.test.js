import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { afterAll, expect, it } from 'vitest';
const require = createRequire(import.meta.url);
const boundary = require('../src/normative/paperLintProcess');
const original = boundary.runPaperLintProcess;
const calls = [];
boundary.runPaperLintProcess = async (_python, args) => {
  calls.push(args);
  if (args[0].endsWith('check_paper_document.py')) {
    const required = ['摘要', '英文摘要', '关键词', '目录', '引言', '主体', '结论', '参考文献'];
    return { stdout: JSON.stringify({ version: 'paper-admission/2.0', status: 'accepted', compiled: true,
      reason_code: 'paper_structure_incomplete', stage: 'partial', reason: '缺少英文摘要（Abstract）。',
      sha256: crypto.createHash('sha256').update(await fs.readFile(args[1])).digest('hex'),
      structure: { status: 'rejected', profile: 'chinese-thesis', required_sections: required,
        missing_sections: ['英文摘要'], incomplete_sections: [],
        observed_sections: Object.fromEntries(required.map(name => [name, name !== '英文摘要'])) } }) };
  }
  return { stdout: JSON.stringify({ schema_version: 'paper-check/1.0',
    publication: { public: { status: 'NO_ALERT', findings: [] } },
    rules: [{ rule_id: '32', status: 'UNKNOWN', counts: {}, results: [] }] }) };
};
const names = ['paperCompilerService', 'paperDocumentAdmission', 'reviewPilotPaperLintService'];
names.forEach(name => { delete require.cache[require.resolve(`../src/normative/${name}`)]; });
const { runCompilerRules } = require('../src/normative/paperCompilerService');
const { runPaperLint } = require('../src/normative/reviewPilotPaperLintService');
const keys = ['PAPER_COMPILER_ENABLED', 'PAPER_COMPILER_PACKAGE_ROOT', 'PAPER_COMPILER_RESULT_ROOT',
  'PAPER_COMPILER_BUDGET_CNY', 'PAPER_COMPILER_PHASE_BUDGET_CNY', 'FIVE_RULE_PYTHON'];
const previous = Object.fromEntries(keys.map(key => [key, process.env[key]]));
const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'partial-compiler-'));
Object.assign(process.env, { PAPER_COMPILER_ENABLED: '1',
  PAPER_COMPILER_PACKAGE_ROOT: path.resolve('paper_compiler/packages'),
  PAPER_COMPILER_RESULT_ROOT: directory, PAPER_COMPILER_BUDGET_CNY: '5',
  PAPER_COMPILER_PHASE_BUDGET_CNY: '5', FIVE_RULE_PYTHON: process.execPath });
afterAll(async () => {
  boundary.runPaperLintProcess = original;
  names.forEach(name => { delete require.cache[require.resolve(`../src/normative/${name}`)]; });
  for (const [key, value] of Object.entries(previous)) {
    if (value === undefined) delete process.env[key]; else process.env[key] = value;
  }
  await fs.rm(directory, { recursive: true, force: true });
});

it.each([false, true])('propagates explicit partial opt-in to the compiler process (%s)', async allowIncompleteStructure => {
  await runCompilerRules('unused.pdf', ['sjtu_rule_32'], { allowIncompleteStructure });
  expect(calls.at(-1).includes('--allow-incomplete-structure')).toBe(allowIncompleteStructure);
});

it('runs bibliography verification for a paper missing only its English abstract', async () => {
  const { result } = await runPaperLint({ pdfBuffer: Buffer.from('%PDF-test'),
    selectedRuleIds: ['sjtu_rule_32'], externalProcessingConsent: true });
  expect(result.document_validation.stage).toBe('partial');
  expect(result.rule_runs[0].execution_status).toBe('completed');
  expect(calls.at(-1)).toContain('--allow-incomplete-structure');
});
