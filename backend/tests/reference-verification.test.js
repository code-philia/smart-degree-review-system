import { describe, it, expect } from 'vitest';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const require = createRequire(import.meta.url);
const { toCompilerResult } = require('../src/normative/paperCompilerService');
const { getCompilerRules } = require('../src/normative/paperCompilerService');
function report(statuses, reasons = []) {
  const results = statuses.map((status, n) => ({ status, node_id: `entry-${n}`, check_id: 'work_existence', reasons: reasons[n] || [], location_mode: 'source', location: { page_number: 1 } }));
  return { schema_version: 'paper-check/1.0', publication: { public: { status: 'NO_ALERT', findings: [] } },
    rules: [{ rule_id: '32', status: statuses.includes('UNKNOWN') ? 'UNKNOWN' : 'PASS', results,
      counts: Object.fromEntries([...new Set(statuses)].map(s => [s, statuses.filter(v => v === s).length])), coverage: { incomplete_scopes: [] } }] };
}
describe('reference verification coverage', () => {
  it('keeps the multisource rule available after SerpAPI quota exhaustion', () => {
    const old = Object.fromEntries(['PAPER_COMPILER_ENABLED','PAPER_COMPILER_PACKAGE_ROOT','PAPER_COMPILER_REFERENCE_LIBRARY'].map(k => [k,process.env[k]]));
    const dir = fs.mkdtempSync(path.join(os.tmpdir(),'reference-availability-'));
    try {
      fs.mkdirSync(path.join(dir,'32')); fs.writeFileSync(path.join(dir,'32/manifest.json'),'{}');
      fs.writeFileSync(path.join(dir,'serpapi-status.json'),JSON.stringify({schema_version:'serpapi-quota-status/1.0',status:'exhausted'}));
      process.env.PAPER_COMPILER_ENABLED='1'; process.env.PAPER_COMPILER_PACKAGE_ROOT=dir; process.env.PAPER_COMPILER_REFERENCE_LIBRARY=dir;
      expect(getCompilerRules().find(r=>r.rule_id==='sjtu_rule_32').available).toBe(true);
    } finally {
      for (const [k,v] of Object.entries(old)) { if (v===undefined) delete process.env[k]; else process.env[k]=v; }
      fs.rmSync(dir,{recursive:true,force:true});
    }
  });
  it('publishes a proven complete reference verification as passed even with NO_ALERT', () => {
    const run = toCompilerResult(report(['PASS', 'PASS']), ['sjtu_rule_32']).rule_runs[0];
    expect(run.outcome).toBe('passed');
    expect(run.params.reference_verification).toMatchObject({ total: 2, verified: 2, unresolved: 0 });
    expect(run.message).toContain('2');
  });
  it('explains provider failures and unmatched entries instead of a generic no-alert message', () => {
    const run = toCompilerResult(report(['PASS', 'UNKNOWN', 'UNKNOWN'], [[], ['reference_lookup_unavailable: openalex=HTTP_429'], ['reference_not_matched']]), ['sjtu_rule_32']).rule_runs[0];
    expect(run.outcome).toBe('inconclusive');
    expect(run.params.reference_verification).toMatchObject({ total: 3, verified: 1, unresolved: 2, unavailable: 1 });
    expect(run.message).toContain('检索服务');
    expect(run.message).not.toBe('未触发告警');
  });
  it('does not infer pass from NO_ALERT without actual entry verification', () => {
    expect(toCompilerResult(report([]), ['sjtu_rule_32']).rule_runs[0].outcome).toBe('inconclusive');
  });
  it('does not hide incomplete bibliography coverage behind passing entries', () => {
    const value = report(['PASS']); value.rules[0].coverage.incomplete_scopes = ['bibliography'];
    expect(toCompilerResult(value, ['sjtu_rule_32']).rule_runs[0].outcome).toBe('inconclusive');
  });
  it('requires an explicit valid coverage record before reporting a complete verification', () => {
    const value=report(['PASS']);delete value.rules[0].coverage;
    expect(toCompilerResult(value,['sjtu_rule_32']).rule_runs[0].outcome).toBe('inconclusive');
  });
});
