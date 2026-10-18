import { afterEach, describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const service = require('../src/normative/paperCompilerService');
const originals = {};
const folders = [];
function env(name, value) { if (!(name in originals)) originals[name] = process.env[name]; process.env[name] = value; }
afterEach(() => { for (const [name, value] of Object.entries(originals)) { if (value === undefined) delete process.env[name]; else process.env[name] = value; delete originals[name]; } for (const folder of folders.splice(0)) fs.rmSync(folder, { recursive: true, force: true }); });
const report = { schema_version: 'paper-check/1.0', pipeline_version: 'pipeline-20261019', runtime: { freeze: true, generation: 3, active_version: 'release-v2' }, rules: [{ rule_id: '31', status: 'PASS', results: [], counts: { PASS: 1 }, coverage: { incomplete_scopes: [] } }] };
function transport(output) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'compiler-online-test-')); folders.push(root);
  const capture = path.join(root, 'argv.json');
  const shim = path.join(root, 'cli-shim');
  fs.writeFileSync(shim, `#!${process.execPath}\nrequire('fs').writeFileSync(${JSON.stringify(capture)},JSON.stringify(process.argv.slice(2)));process.stdout.write(${JSON.stringify(JSON.stringify(output))});\n`, { mode: 0o700 });
  env('PAPER_COMPILER_PYTHON', shim); env('PAPER_COMPILER_CONTROL_ROOT', path.join(root, 'control'));
  env('PAPER_COMPILER_RESULT_ROOT', path.join(root, 'results')); env('PAPER_COMPILER_PACKAGE_ROOT', path.join(root, 'packages')); env('PAPER_COMPILER_ENABLED', '1');
  fs.mkdirSync(path.join(root, 'packages', '31'), { recursive: true }); fs.writeFileSync(path.join(root, 'packages', '31', 'manifest.json'), '{}');
  return { root, capture };
}
describe('online compiler CLI boundary', () => {
  it('normalizes the CLI history envelope to the HTTP event array', async () => {
    transport({ events: [{ action: 'set_freeze', freeze: true }] });
    expect(await service.runCompilerControl('history')).toEqual([{ action: 'set_freeze', freeze: true }]);
  });

  it('routes only cache artifacts to the configured root while retaining the shared ledger default', async () => {
    const { root, capture } = transport(report);
    env('PAPER_COMPILER_CACHE_ROOT', path.join(root, 'online-cache'));
    await service.runCompilerRules('/data/tmp/input.pdf', ['sjtu_rule_31']);
    const argv = JSON.parse(fs.readFileSync(capture, 'utf8'));
    expect(argv[argv.indexOf('--cache') + 1]).toBe(path.join(root, 'online-cache'));
    expect(argv).not.toContain('--ledger');
  });
  it('reports unavailable management when the compiler has not been enabled', async () => {
    const { capture } = transport({ freeze: false, generation: 0, active_version: null, active_path: null });
    env('PAPER_COMPILER_ENABLED', '0');
    await expect(service.runCompilerControl('status')).rejects.toMatchObject({ status: 503, code: 'COMPILER_UNAVAILABLE' });
    expect(fs.existsSync(capture)).toBe(false);
  });

  it('runs detection online with both cumulative and phase budgets capped at 200', async () => {
    const { capture, root } = transport(report);
    const result = await service.runCompilerRules('/data/tmp/input.pdf', ['sjtu_rule_31']);
    const argv = JSON.parse(fs.readFileSync(capture, 'utf8'));
    expect(argv).toContain('--online'); expect(argv).toContain('--stdout-report');
    expect(argv[argv.indexOf('--control-root') + 1]).toBe(path.join(root, 'control'));
    expect(argv[argv.indexOf('--phase-budget') + 1]).toBe('200');
    expect(argv[argv.indexOf('--budget') + 1]).toBe('200');
    expect(result.ruleset.version_label).toContain('release-v2');
    expect(result.rule_runs[0].runtime_version).toBe('release-v2');
    expect(result.rule_runs[0].pipeline_version).toBe('pipeline-20261019');
    expect(result.runtime).toEqual({ freeze: true, generation: 3, active_version: 'release-v2' });
    expect(result.rule_runs[0].runtime_snapshot).toEqual(result.runtime);
  });
  it('uses actual pipeline metadata when no runtime version exists', () => {
    const value = { ...report, runtime: undefined };
    expect(service.toCompilerResult(value, ['sjtu_rule_31']).ruleset.version_label).toContain('pipeline-20261019');
  });
  it('keeps compiler versions when merged with the existing rules', () => {
    const { mergePaperLintResults } = require('../src/normative/reviewPilotPaperLintService');
    const compiler = service.toCompilerResult(report, ['sjtu_rule_31']);
    const existing = { rule_runs: [{ rule_id: 'sjtu_rule_18', execution_status: 'completed', outcome: 'passed', severity: 'warning', findings: [] }] };
    const mixed = mergePaperLintResults(existing, compiler, ['sjtu_rule_18', 'sjtu_rule_31']);
    expect(mixed.ruleset.version_label).toContain('release-v2');
    expect(mixed.runtime).toEqual({ freeze: true, generation: 3, active_version: 'release-v2' });
  });
  it('calls the fixed control CLI without passing a PDF or compile operation', async () => {
    const snapshot = { freeze: true, generation: 2, active_version: 'v1', active_path: '/data/runtime/packages/v1' };
    const { capture, root } = transport(snapshot);
    expect(typeof service.runCompilerControl).toBe('function');
    expect(await service.runCompilerControl('freeze')).toEqual(snapshot);
    const argv = JSON.parse(fs.readFileSync(capture, 'utf8'));
    expect(argv.slice(1)).toEqual(['control', '--action', 'freeze', '--control-root', path.join(root, 'control')]);
  });
  it('supports a history array and rollback version as separate CLI arguments', async () => {
    const { capture } = transport([{ action: 'set_freeze', freeze: true }]);
    expect(typeof service.runCompilerControl).toBe('function');
    expect(await service.runCompilerControl('history')).toEqual([{ action: 'set_freeze', freeze: true }]);
    transport({ freeze: false, generation: 2, active_version: 'v1', active_path: '/data/runtime/packages/v1' });
    await service.runCompilerControl('rollback', { version: 'v1' });
    const argv = JSON.parse(fs.readFileSync(folders.at(-1) + '/argv.json', 'utf8'));
    expect(argv.slice(-2)).toEqual(['--version', 'v1']);
  });
  it('rejects unsupported control actions and missing rollback versions before spawning', async () => {
    expect(typeof service.runCompilerControl).toBe('function');
    await expect(service.runCompilerControl('compile')).rejects.toMatchObject({ status: 400 });
    await expect(service.runCompilerControl('rollback')).rejects.toMatchObject({ status: 400 });
  });
});
