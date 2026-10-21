import { expect, it } from 'vitest';
import { createRequire } from 'node:module';
import { createHash } from 'node:crypto';
const require=createRequire(import.meta.url);
const {buildMessages}=require('../src/normative/repairModelProposalService');
const clone=value=>JSON.parse(JSON.stringify(value));
function fixture() {
 const current={schema_version:'repair-request-v1',source:{kind:'legacy_archive',job_id:'job',document_id:'doc',document_sha256:'a'.repeat(64),detector_version:'detector'},
  rule:{rule_id:'sjtu_rule_15',text:'出现未被引用的图。',version:'legacy-rule-text-20261018'},
  finding:{finding_id:'f',message:'图1未被引用',location:{type:'pdf_page',page_number:1,text_excerpt:'图1 实验流程'},anchors:[]},
  evidence:[{evidence_id:'legacy-evidence-1',source_kind:'pdf_text',text:'图1 实验流程',page_number:1,source_ref:'legacy_archive:finding_location'},
    {evidence_id:'pdf-context-2',source_kind:'pdf_text',text:'这里介绍实验流程。图1 实验流程',page_number:1,source_ref:'legacy_archive:pdf_context:paper.pdf#page=1&relation=target'}],
  context_sha256:'b'.repeat(64),source_identity_sha256:'c'.repeat(64)};
 const original=clone(current);delete original.source_identity_sha256;
 original.context_sha256=createHash('sha256').update(JSON.stringify({rule_id:'sjtu_rule_15',finding_id:'f',message:'图1未被引用',
   evidence:original.evidence.map(({evidence_id,source_kind,text,page_number,source_ref})=>({evidence_id,source_kind,text,page_number,source_ref}))})).digest('hex');
 const response={schema_version:'repair-response-v2',source:clone(original.source),rule_id:'sjtu_rule_15',finding_id:'f',status:'suggested',
   actions:[{instruction:'补充对图1的引用',evidence_ids:['pdf-context-2']}],
   provenance:{provider:'huawei_maas',model:'model',model_version:'version',prompt_version:'repair-model-actions-v3',context_sha256:original.context_sha256,generated_at:'2026-10-21T00:00:00Z'},usage:{input_tokens:10,output_tokens:10,attempts:1}};
 return {current,record:{source:{jobId:'job',documentId:'doc',ruleId:'sjtu_rule_15',findingId:'f'},relative_path:'paper.pdf',request:original,prompt_messages:buildMessages(current),response},
   proof:{pdfSha256:'a'.repeat(64),document:{relative_path:'paper.pdf',result:{execution_provenance:{pdf_sha:'a'.repeat(64)}}},batchSha256:'d'.repeat(64),inputName:'batch.json'}};
}
async function verify(value) { const {verifyBatchRepairRecord}=await import('../src/normative/repairBatchImport.js');return verifyBatchRepairRecord(value.record,value.current,value.proof); }
it('preserves original actions and generation provenance while adding a verified current cache binding',async()=>{
 const f=fixture();const before=clone(f.record.response);const bound=await verify(f);
 expect(bound.actions).toEqual(before.actions);expect(bound.source).toEqual(before.source);
 expect(bound.provenance).toMatchObject({...before.provenance,source_identity_sha256:'c'.repeat(64),cache_context_sha256:'b'.repeat(64),verified_pdf_sha256:'a'.repeat(64),import_batch_sha256:'d'.repeat(64)});
 expect(f.record.response).toEqual(before);
});
it('rejects a batch whose actual current PDF hash or alert excerpt changed',async()=>{
 const f=fixture();f.proof.pdfSha256='e'.repeat(64);await expect(verify(f)).rejects.toThrow(/PDF/);
 const g=fixture();g.current.finding.location.text_excerpt='另一条图题';await expect(verify(g)).rejects.toThrow(/finding/);
});
it('rejects tampered original source, model prompt, response binding, and evidence IDs',async()=>{
 for(const mutate of [
   f=>{f.record.response.source.document_id='other';},
   f=>{f.record.prompt_messages[0].content='altered prompt';},
   f=>{f.record.request.context_sha256='f'.repeat(64);},
   f=>{f.record.response.actions[0].evidence_ids=['not-provided'];},
 ]){const f=fixture();mutate(f);await expect(verify(f)).rejects.toThrow();}
});
it('accepts a verified old path-hash identity only with exact current PDF context and correct fallback formula',async()=>{
 const f=fixture();const fallback=createHash('sha256').update('job:doc:paper.pdf').digest('hex');
 f.proof.document.result={};f.current.source.document_sha256=fallback;f.record.request.source.document_sha256=fallback;f.record.response.source.document_sha256=fallback;
 const bound=await verify(f);expect(bound.provenance.verified_pdf_sha256).toBe('a'.repeat(64));
 f.record.request.evidence[1].text='不同上下文';await expect(verify(f)).rejects.toThrow();
});

it('accepts original upstream evidence ordering without changing saved messages',async()=>{
 const f=fixture();const message=JSON.parse(f.record.prompt_messages[1].content);
 message.evidence.sort((a,b)=>a.evidence_id.localeCompare(b.evidence_id));
 f.record.prompt_messages[1].content=JSON.stringify(message);
 const before=clone(f.record.prompt_messages);
 expect(message.evidence[0].evidence_id).toBe('legacy-evidence-1');
 await expect(verify(f)).resolves.toMatchObject({status:'suggested'});
 expect(f.record.prompt_messages).toEqual(before);
});
it('rejects altered or omitted visible evidence even when upstream evidence ordering differs',async()=>{
 for(const mutate of [
   m=>{m.evidence[0].text='changed visible text';},
   m=>{m.evidence.pop();},
   m=>{m.finding.message='changed alert';},
 ]) {const f=fixture();const message=JSON.parse(f.record.prompt_messages[1].content);
   message.evidence.reverse();mutate(message);f.record.prompt_messages[1].content=JSON.stringify(message);
   await expect(verify(f)).rejects.toThrow(/model prompt/);
 }
});
