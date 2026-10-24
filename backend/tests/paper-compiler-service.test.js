import { describe, it, expect } from 'vitest';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const service = require('../src/normative/paperCompilerService');
const raw = (status = 'UNKNOWN') => ({ schema_version: 'paper-check/1.0', rules: [{ rule_id: '31', title: '格式', status, counts: { UNKNOWN: 1 }, coverage: { incomplete_scopes: ['bibliography'] }, results: [{ check_id: 'c', node_id: 'n', status, message: 'Missing title', reasons: ['evidence unavailable'], location: null, location_mode: 'synthetic', display_evidence: [] }] }] });
describe('compiler adapter', () => {
  it('keeps unknown as inconclusive and synthetic locations off the PDF', () => {
    const result = service.toCompilerResult(raw(), ['sjtu_rule_31']);
    expect(result.rule_runs[0].outcome).toBe('inconclusive');
    expect(result.rule_runs[0].findings).toEqual([]);
    expect(result.rule_runs[0].compiler_diagnostics[0].status).toBe('UNKNOWN');
    const found = service.toCompilerResult(raw('VIOLATION'), ['sjtu_rule_31']).rule_runs[0];
    expect(found.findings[0].location).toBeNull();
    expect(found.evidence_mode).toBe('derived');
  });
  it('rejects partial terminal records', () => {
    expect(() => service.toCompilerResult(raw(), ['sjtu_rule_31','sjtu_rule_32'])).toThrow();
  });
  it('advertises disabled compiler rules as unavailable', async () => {
    const old=process.env.PAPER_COMPILER_ENABLED;delete process.env.PAPER_COMPILER_ENABLED;
    try { expect(service.getCompilerRules().every(r=>!r.available && r.uses_external_model)).toBe(true);
      await expect(service.runCompilerRules('/tmp/x.pdf',['sjtu_rule_31'])).rejects.toMatchObject({status:503});
    } finally { if(old!==undefined)process.env.PAPER_COMPILER_ENABLED=old; }
  });
  it('rejects malformed and oversized child output', async () => {
    await expect(service.runJsonProcess(process.execPath,['-e',"process.stdout.write('oops')"])).rejects.toMatchObject({code:'COMPILER_INVALID_JSON'});
    await expect(service.runJsonProcess(process.execPath,['-e',"process.stdout.write('x'.repeat(20000))"],{maxBytes:1024})).rejects.toMatchObject({code:'COMPILER_OUTPUT_LIMIT'});
  });
  it('bounds timeout and honors cancellation', async () => {
    await expect(service.runJsonProcess(process.execPath,['-e','setInterval(()=>{},1000)'],{timeoutMs:30})).rejects.toMatchObject({status:504});
    const c=new AbortController();c.abort();
    await expect(service.runJsonProcess(process.execPath,['-e','console.log(1)'],{signal:c.signal})).rejects.toMatchObject({status:504});
  });
});

it('preserves normative basis for findings and uncertain diagnostics',()=>{
  const value=raw('VIOLATION');value.rules[0].basis_catalog=[{id:'gbt7714-2025:8.7',text:'Degree granting institution required',kind:'standard'}];
  value.rules[0].results[0].basis=['gbt7714-2025:8.7'];
  const found=service.toCompilerResult(value,['sjtu_rule_31']).rule_runs[0].findings[0];
  expect(found.basis_details[0].id).toBe('gbt7714-2025:8.7');
  expect(found.basis_details[0].kind).toBe('standard');
});
