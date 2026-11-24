import { expect, it, vi } from 'vitest';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const { runReferenceVerification, referenceVerificationRule } = require('../src/normative/referenceVerificationService');
const entry = { id:'entry-1', text:'[1] Example source.', title:'Example source', authors:['Author A'],year:2024,location:{type:'pdf_page',page_number:5,text_excerpt:'[1] Example source.'} };
const extracted = { entries:[entry], coverage_complete:true, native_only:true };

it('keeps verified entries in structured results without fabricating a finding', async()=>{
  const result=await runReferenceVerification('unused.pdf', {extractor:async()=>extracted,credentials:{personalKey:'private'},
    verify:async()=>({category:'verified',reason_code:'matched',sources:[],comparisons:[],coverage:{complete:true}})});
  const run=result.rule_runs[0];
  expect(run.rule_id).toBe('reference_verification_check');
  expect(run.outcome).toBe('passed');expect(run.findings).toEqual([]);
  expect(run.params.reference_verification.entries[0].entry.location.page_number).toBe(5);
  expect(JSON.stringify(result)).not.toContain('private');
  expect(referenceVerificationRule.uses_external_model).toBe(false);
});

it('keeps extraction gaps unverified and preserves native location plus source evidence',async()=>{
  const result=await runReferenceVerification('unused.pdf',{extractor:async()=>({...extracted,coverage_complete:false}),credentials:{personalKey:'private'},
    verify:async()=>({category:'mismatch',reason_code:'metadata_mismatch',comparisons:[{field:'year',cited:2024,matched:2023,status:'different'}],sources:[{provider:'crossref',url:'https://doi.org/10.1234/example',status:'ok'}],coverage:{complete:true}})});
  const run=result.rule_runs[0];expect(run.findings[0].location).toEqual(entry.location);
  expect(run.findings[0].reference_check.category).toBe('mismatch');
  expect(run.findings[0].evidence[0].url).toBe('https://doi.org/10.1234/example');
  expect(run.coverage.incomplete_scopes).toContain('bibliography');
  expect(run.outcome).toBe('issues_found');
});

it('does not treat an empty unreadable bibliography as passed',async()=>{
  const result=await runReferenceVerification('unused.pdf',{extractor:async()=>({entries:[],coverage_complete:false}),credentials:{personalKey:'private'},verify:vi.fn()});
  const run=result.rule_runs[0];expect(run.outcome).toBe('inconclusive');
  expect(run.findings[0].reference_check.category).toBe('unverified');
});
it('counts an explicit unverified-entry result once rather than adding a duplicate generic execution warning',async()=>{
  const {displayedReportSummary}=await import('../../shared/paper-lint-presentation.mjs');
  const result=await runReferenceVerification('unused.pdf',{extractor:async()=>extracted,credentials:{personalKey:'private'},verify:async()=>({category:'unverified',reason_code:'provider_unavailable',sources:[],comparisons:[],coverage:{complete:false}})});
  expect(displayedReportSummary(result)).toMatchObject({finding_count:1,execution_warning_count:0});
});

it('sanitizes per-entry failures but propagates task cancellation',async()=>{
  const options={extractor:async()=>extracted,credentials:{personalKey:'private'},verify:async()=>{throw new Error('secret-key-in-upstream-error');}};
  const result=await runReferenceVerification('unused.pdf',options);
  expect(result.rule_runs[0].findings[0].reference_check.category).toBe('unverified');
  expect(JSON.stringify(result)).not.toContain('secret-key');
  const controller=new AbortController();controller.abort();
  await expect(runReferenceVerification('unused.pdf',{...options,signal:controller.signal})).rejects.toMatchObject({name:'AbortError'});
});
it('redacts private credentials even if an extracted PDF entry echoes them',async()=>{
  const result=await runReferenceVerification('unused.pdf',{extractor:async()=>({...extracted,entries:[{...entry,text:'source private-api-key',location:{type:'pdf_page',page_number:5,text_excerpt:'private-api-key'}}]}),credentials:{personalKey:'private-api-key'},
    verify:async()=>({category:'unverified',reason_code:'not_found',sources:[],comparisons:[],coverage:{complete:false}})});
  expect(JSON.stringify(result)).not.toContain('private-api-key');
});
