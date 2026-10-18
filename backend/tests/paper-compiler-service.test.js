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

 it('dispatches old and compiler rules together while requiring external consent', async()=>{
  const local=require('../src/normative/localFiveRulePaperLintService');
  const filename=require.resolve('../src/normative/reviewPilotPaperLintService');
  const previous=require.cache[filename];const oldLocal=local.runLocalFiveRules;const oldCatalog=service.getCompilerRules;const oldRun=service.runCompilerRules;
  const oldDir=process.env.REVIEW_PILOT_BACKEND_DIR;process.env.REVIEW_PILOT_BACKEND_DIR='/nonexistent-compiler-test-backend';
  let localCalls=0,compilerCalls=0;
  local.runLocalFiveRules=async()=>{localCalls++;return {rule_runs:[{rule_id:'sjtu_rule_18',execution_status:'completed',outcome:'passed',severity:'warning',findings:[]}]};};
  service.getCompilerRules=()=>oldCatalog().map(r=>({...r,available:true}));
  service.runCompilerRules=async()=>{compilerCalls++;return service.toCompilerResult(raw(),['sjtu_rule_31']);};
  delete require.cache[filename];
  try {
    const mixed=require(filename);const input={pdfBuffer:Buffer.from('%PDF-1.7\n'),selectedRuleIds:['sjtu_rule_18','sjtu_rule_31']};
    await expect(mixed.runPaperLint(input)).rejects.toMatchObject({status:400});
    expect(localCalls+compilerCalls).toBe(0);
    const result=await mixed.runPaperLint({...input,externalProcessingConsent:true});
    expect(localCalls).toBe(1);expect(compilerCalls).toBe(1);
    expect(result.result.rule_runs.map(r=>r.rule_id)).toEqual(input.selectedRuleIds);
    expect(result.result.rule_runs[1].outcome).toBe('inconclusive');
  } finally {local.runLocalFiveRules=oldLocal;service.getCompilerRules=oldCatalog;service.runCompilerRules=oldRun;
    if(previous)require.cache[filename]=previous;else delete require.cache[filename];
    if(oldDir===undefined)delete process.env.REVIEW_PILOT_BACKEND_DIR;else process.env.REVIEW_PILOT_BACKEND_DIR=oldDir;
  }
 });
