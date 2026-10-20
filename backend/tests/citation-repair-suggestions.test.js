import { describe, expect, it } from 'vitest';
import { createRequire } from 'node:module';
const require=createRequire(import.meta.url);
const { buildLegacyRepairRequest, buildPaperLintReportRepairRequest }=require('../src/normative/legacyRepairAdapter');
const { buildMessages }=require('../src/normative/repairModelProposalService');
const { toCompilerResult }=require('../src/normative/paperCompilerService');
const ids=['sjtu_rule_31','sjtu_rule_32','sjtu_rule_33'];
function finding() {return {finding_id:'f1',message:'待核对的引用问题',location:{page_number:1,text_excerpt:'原文引用 [1]'},anchors:[],evidence:[
  {id:'source',kind:'source_span',quote:'原文引用 [1]'},
  ...Array.from({length:12},(_,i)=>({id:`basis-${i}`,kind:'normative_span',quote:`适用规范第${i}条`})),
  {id:'external',kind:'external_source',quote:'已提供的被引文献内容',provider:'controlled',url:'https://example.test/work'},
]};}
function build(ruleId, mode='archive', f=finding()) {
 const values={ruleRun:{rule_id:ruleId,package_sha256:'package-v1',pipeline_version:'pipeline-v1'},finding:f};
 return mode==='archive'?buildLegacyRepairRequest({...values,job:{id:'job'},document:{id:'doc',relative_path:'paper.pdf',result:{}}}):
  buildPaperLintReportRepairRequest({...values,report:{id:'report',result:{}},documentSha256:'a'.repeat(64)});
}
describe('citation-rule repair requests',()=>{
 it.each(ids.flatMap(id=>[[id,'archive'],[id,'report']]))('supports %s in %s results', (id,mode)=>{
  const request=build(id,mode);expect(request.rule.rule_id).toBe(id);expect(request.rule.text).toBeTruthy();
  expect(request.source_identity_sha256).toHaveLength(64);
 });
 it.each(ids)('passes citation and normative evidence to the bounded model input for %s',id=>{
  const request=build(id);const input=buildMessages(request)[1].content;
  expect(input).toContain('已提供的被引文献内容');expect(input).toContain('适用规范第11条');
  expect(input).toContain('https://example.test/work');
 });
 it('invalidates cached advice when the cited content changes',()=>{
  const first=build('sjtu_rule_33');const changed=finding();changed.evidence.at(-1).quote='更正后的被引内容';
  expect(build('sjtu_rule_33','archive',changed).source_identity_sha256).not.toBe(first.source_identity_sha256);
 });
 it('keeps the distinction between unavailable retrieval and confirmed nonexistence',()=>{
  expect(build('sjtu_rule_32').rule.text).toMatch(/查不到.*不能.*不存在/);
  expect(build('sjtu_rule_33').rule.text).toContain('不得编造');
 });
});

function projectedRequest(id, proof, versions={}) {
 const output={schema_version:'paper-check/1.0',runtime_version:'runtime-v1',pipeline_version:'pipeline-v1',...versions,
  rules:[{rule_id:id.slice(10),status:'VIOLATION',package_sha256:'package-v1',results:[{node_id:'n',status:'VIOLATION',location_mode:'source',location:{page_number:1,text_excerpt:'待核对引用 [1]'}}]}],
  publication:{public:{status:'ALERT',findings:[{rule_id:id.slice(10),node_id:'n',message:'核验发现引用问题',evidence:[[proof]]}]}}};
 const ruleRun=toCompilerResult(output,[id]).rule_runs[0];
 return {ruleRun,request:buildLegacyRepairRequest({job:{id:'job'},document:{id:'doc',result:{}},ruleRun,finding:ruleRun.findings[0]})};
}
function catalogProof() {return {id:'catalog-exclusion-test',kind:'controlled_catalog_scope',domain:'controlled_catalog',complete:true,
 search_scope:'controlled_catalog:scope-v1',query:{title:'Missing Work',authors:['Example Author'],year:2025,doi:null},
 catalog:[{id:'known-work',title:'Known Work',authors:['Example Author'],year:2024}],protocol:'complete-catalog-title-author-year/1.0'};}
describe('producer-to-repair citation provenance',()=>{
 it('retains the exact R32 controlled-catalog proof scope without sending the catalog',()=>{
  const {ruleRun,request}=projectedRequest('sjtu_rule_32',catalogProof());
  const entry=ruleRun.findings[0].evidence[0];
  expect(entry.search_scope).toBe('controlled_catalog:scope-v1');expect(entry.complete).toBe(true);
  expect(entry.catalog_size).toBe(1);expect(entry.proof_sha256).toHaveLength(64);expect(entry.catalog).toBeUndefined();
  const input=buildMessages(request)[1].content;
  expect(input).toContain('controlled_catalog:scope-v1');expect(input).toContain('Missing Work');
  expect(input).toContain('仅限该受控文献库');expect(input).not.toContain('Known Work');
  expect(request.rule.text).toContain('完整受控文献库');
 });
 it.each(['search_scope','complete','catalog'])('invalidates R32 advice when proof %s changes',key=>{
  const initial=projectedRequest('sjtu_rule_32',catalogProof()).request;const changed=catalogProof();
  if(key==='search_scope') changed.search_scope='controlled_catalog:scope-v2';
  if(key==='complete') changed.complete=false;
  if(key==='catalog') changed.catalog[0].title='Another Known Work';
  expect(projectedRequest('sjtu_rule_32',changed).request.source_identity_sha256).not.toBe(initial.source_identity_sha256);
 });
 it('binds R33 quoted content to its actual work identity and omits full source text',()=>{
  const proof={id:'span',kind:'external_span',source_id:'content:1',origin:'external',start:0,end:6,
   quote:'被引内容片段',source_sha256:'a'.repeat(64),content_id:'content-1',work_id:'work-1',source_text:'PRIVATE_FULL_TEXT'};
  const {ruleRun,request}=projectedRequest('sjtu_rule_33',proof);
  expect(ruleRun.findings[0].evidence[0].source_text).toBeUndefined();
  expect(buildMessages(request)[1].content).toContain('work-1');
  expect(buildMessages(request)[1].content).not.toContain('PRIVATE_FULL_TEXT');
  expect(projectedRequest('sjtu_rule_33',{...proof,work_id:'work-2'}).request.source_identity_sha256).not.toBe(request.source_identity_sha256);
 });
 it.each(['runtime_version','pipeline_version'])('invalidates citation advice on %s changes with an unchanged package',key=>{
  const first=projectedRequest('sjtu_rule_32',catalogProof()).request;
  const second=projectedRequest('sjtu_rule_32',catalogProof(),{[key]:'v2'}).request;
  expect(second.source_identity_sha256).not.toBe(first.source_identity_sha256);
 });
});
