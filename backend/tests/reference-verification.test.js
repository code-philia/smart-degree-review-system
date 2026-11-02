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
    expect(run.message).toBe('未发现疑似不存在的引用。');
  });
  it('keeps insufficient evidence internally without presenting it as a suspected reference', () => {
    const run = toCompilerResult(report(['PASS', 'UNKNOWN', 'UNKNOWN'], [[], ['reference_lookup_unavailable: openalex=HTTP_429'], ['reference_not_matched']]), ['sjtu_rule_32']).rule_runs[0];
    expect(run.outcome).toBe('inconclusive');
    expect(run.params.reference_verification).toMatchObject({ total: 3, verified: 1, unresolved: 2, unavailable: 1 });
    expect(run.message).toBe('未发现疑似不存在的引用。');
    expect(run.findings).toEqual([]);
    expect(run.compiler_diagnostics).toHaveLength(2);
    expect(run.severity).toBe('info');
  });
  it('does not promote a legacy SerpAPI search miss into a review prompt', () => {
    const run = toCompilerResult(report(['UNKNOWN'], [['serpapi_not_found']]), ['sjtu_rule_32']).rule_runs[0];
    expect(run.findings).toEqual([]);
    expect(run.compiler_diagnostics).toHaveLength(1);
    expect(run.message).toBe('未发现疑似不存在的引用。');
  });
  it('lists only publication-supported references as individual informational review items', () => {
    const value = report(['VIOLATION', 'VIOLATION', 'UNKNOWN']);
    value.rules[0].status = 'VIOLATION';
    value.publication.public = { status: 'ALERT', findings: [0, 1].map(n => ({ rule_id: '32', node_id: `entry-${n}`,
      message: `有完整目录证据支持的疑点 ${n + 1}`, evidence: [[{ kind: 'source_span', quote: `[${n + 1}] 原始参考文献 ${n + 1}` }]] })) };
    const result = toCompilerResult(value, ['sjtu_rule_32']);
    const run = result.rule_runs[0];
    expect(run.severity).toBe('info');
    expect(run.findings).toHaveLength(2);
    expect(run.findings.every(f => f.prompt_only && f.reference_review === 'supported_suspicion')).toBe(true);
    expect(run.findings.every(f => f.suggestion.includes('人工复核'))).toBe(true);
    expect(run.findings.map(f => f.location.page_number)).toEqual([1, 1]);
    expect(run.findings[0].evidence[0].quote).toBe('[1] 原始参考文献 1');
    expect(result.summary).toMatchObject({ info_finding_count: 2, warning_finding_count: 0, error_finding_count: 0 });
  });
  it('does not publish a proposed exclusion rejected by the publication gate', () => {
    const run = toCompilerResult(report(['VIOLATION']), ['sjtu_rule_32']).rule_runs[0];
    expect(run.findings).toEqual([]);
    expect(run.message).toBe('未发现疑似不存在的引用。');
  });
  it('retains the execution failure message without publication metadata', () => {
    const value = report([]); delete value.publication;
    value.rules[0].status = 'ERROR';
    value.rules[0].execution_error = { error_type: 'ProgramError', reason: 'broken detector execution' };
    const run = toCompilerResult(value, ['sjtu_rule_32']).rule_runs[0];
    expect(run.execution_status).toBe('error');
    expect(run.message).toContain('broken detector execution');
    expect(run.message).not.toContain('未发现');
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
