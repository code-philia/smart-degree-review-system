import { expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const {buildMessages,validateModelAnswer}=require('../src/normative/repairModelProposalService');
function citationRequest(large=false) {
  return {
    rule:{rule_id:'sjtu_rule_33',text:'引用语境应与被引内容相符',version:'citation'},
    finding:{finding_id:'f',message:'引用不相关'},
    evidence:[
      {evidence_id:'original',source_kind:'pdf_text',source_ref:'legacy_archive:finding_location',text:'论文原句'},
      ...Array.from({length:5},(_,i)=>({evidence_id:'content-'+i,source_kind:'retrieval',source_ref:'paper_compiler:external_span:'+i,text:large?'文献证据'.repeat(1500):'被引内容'+i})),
      {evidence_id:'normative',source_kind:'retrieval',source_ref:'paper_compiler:normative',text:'规范依据'},
      ...['before','target','after'].map(relation=>({evidence_id:'context-'+relation,source_kind:'pdf_text',source_ref:'legacy_archive:pdf_context:paper#page=2&relation='+relation,text:'邻近PDF原文'})),
    ],
  };
}
it('keeps original, all five cited contents, and normative evidence before optional adjacent context',()=>{
 const request=citationRequest();
 const evidence=JSON.parse(buildMessages(request)[1].content).evidence;
 expect(evidence.map(item=>item.evidence_id)).toEqual(expect.arrayContaining(['original','content-0','content-1','content-2','content-3','content-4','normative']));
 expect(evidence.length).toBeLessThanOrEqual(8);
 expect(()=>validateModelAnswer({status:'suggested',actions:[{instruction:'核对被引内容',evidence_ids:['content-4','normative']}]},request)).not.toThrow();
});
it('does not lose critical cited evidence and normative text when prior content exhausts the character budget',()=>{
 const evidence=JSON.parse(buildMessages(citationRequest(true))[1].content).evidence;
 expect(evidence.find(item=>item.evidence_id==='normative')?.text).toBe('规范依据');
 expect(evidence.find(item=>item.evidence_id==='content-4')?.text.length).toBeGreaterThan(0);
 expect(evidence.reduce((sum,item)=>sum+item.text.length,0)).toBeLessThanOrEqual(12000);
});

it('preserves source identity and URL after a long quoted citation within the character budget',()=>{
 const request=citationRequest(true);
 for(const [i,item] of request.evidence.filter(e=>e.evidence_id.startsWith('content-')).entries()) {
   item.text+='\n来源标识：'+JSON.stringify({work_id:'actual-work-'+i,source_sha256:'a'.repeat(64)})+'\n来源链接：https://example.org/work/'+i;
 }
 const evidence=JSON.parse(buildMessages(request)[1].content).evidence;
 for(let i=0;i<5;i++) {
   const item=evidence.find(e=>e.evidence_id==='content-'+i);
   expect(item.text).toContain('actual-work-'+i);
   expect(item.text).toContain('a'.repeat(64));
   expect(item.text).toContain('https://example.org/work/'+i);
 }
 expect(evidence.reduce((sum,item)=>sum+item.text.length,0)).toBeLessThanOrEqual(12000);
});
